"""Redeem credits — the concurrency-critical path.

How two simultaneous redeems are kept from overspending:
  1. Lock the driver row (SELECT ... FOR UPDATE). A second redeem for the same
     driver waits here until the first commits or rolls back.
  2. Only then read the driver's unexpired rides and check the balance, so the
     check always sees the result of any redeem that ran before it.
  3. Spend rides' credits oldest-expiry first, write one debit ledger entry
     (that entry IS the redemption), record which rides it drew on, commit.
     All in one transaction.
The CHECK (credits_remaining >= 0) constraint is the last line of defence.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import EntryType
from app.exceptions import (
    DriverNotFoundException,
    IdempotencyConflictException,
    InsufficientBalanceException,
)
from app.models import Driver, LedgerEntry, RedemptionAllocation, Ride
from app.schemas.redemptions import ConsumedRide, RedeemRequest, RedemptionResource
from app.services.credit_policy import format_credits, to_milli
from app.services.driver_service import available_balance


def redeem(
    db: Session, driver_id: str, data: RedeemRequest, idempotency_key: str | None = None
) -> tuple[RedemptionResource, bool]:
    """Returns (redemption, created). created=False = idempotent replay.

    idempotency_key (from the Idempotency-Key header) is optional. Without it a
    retried request is a new redemption — the server cannot tell a retry from a
    genuine second redeem. Concurrency safety never depends on it.
    """
    amount = to_milli(data.amount)

    with db.begin():
        # 1. lock the driver — serialises every redeem for this driver
        locked = db.scalar(select(Driver.id).where(Driver.id == driver_id).with_for_update())
        if locked is None:
            raise DriverNotFoundException(driver_id)

        # Replay of a redeem we already did? Return it instead of spending again.
        if idempotency_key:
            previous = db.scalar(
                select(LedgerEntry).where(
                    LedgerEntry.driver_id == driver_id,
                    LedgerEntry.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if previous.amount != amount:
                    raise IdempotencyConflictException(idempotency_key)
                return _to_resource(db, previous), False

        # 2. read spendable rides, oldest expiry first
        rides = db.scalars(
            select(Ride)
            .where(
                Ride.driver_id == driver_id,
                Ride.expires_at > func.now(),
                Ride.credits_remaining > 0,
            )
            .order_by(Ride.expires_at, Ride.ride_id)
        ).all()

        available = sum(r.credits_remaining for r in rides)
        if available < amount:
            raise InsufficientBalanceException(format_credits(available), format_credits(amount))

        # 3. spend FIFO
        taken: list[tuple[str, int]] = []
        still_needed = amount
        for ride in rides:
            if still_needed == 0:
                break
            take = min(ride.credits_remaining, still_needed)
            ride.credits_remaining -= take
            still_needed -= take
            taken.append((ride.ride_id, take))

        reason = f"Redeemed {format_credits(amount)} credits"
        if data.reason:
            reason += f": {data.reason}"
        debit = LedgerEntry(
            driver_id=driver_id,
            entry_type=EntryType.DEBIT.value,
            amount=amount,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        db.add(debit)
        db.flush()  # get debit.id
        db.add_all(
            RedemptionAllocation(ledger_entry_id=debit.id, ride_id=ride_id, amount=take)
            for ride_id, take in taken
        )
        db.flush()
        return _to_resource(db, debit), True


def _to_resource(db: Session, debit: LedgerEntry) -> RedemptionResource:
    consumed = db.execute(
        select(RedemptionAllocation.ride_id, RedemptionAllocation.amount, Ride.expires_at)
        .join(Ride, Ride.ride_id == RedemptionAllocation.ride_id)
        .where(RedemptionAllocation.ledger_entry_id == debit.id)
        .order_by(RedemptionAllocation.id)
    ).all()
    return RedemptionResource(
        redemption_id=debit.id,
        driver_id=debit.driver_id,
        amount=format_credits(debit.amount),
        reason=debit.reason,
        balance_after=format_credits(available_balance(db, debit.driver_id)),
        consumed=[
            ConsumedRide(ride_id=r.ride_id, amount=format_credits(r.amount), expires_at=r.expires_at)
            for r in consumed
        ],
        created_at=debit.created_at,
    )
