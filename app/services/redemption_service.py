"""Redeem credits — the concurrency-critical path.

How two simultaneous redeems are kept from overspending:
  1. Lock the driver row (SELECT ... FOR UPDATE). A second redeem for the same
     driver waits here until the first commits or rolls back.
  2. Only then read the driver's unexpired lots and check the balance, so the
     check always sees the result of any redeem that ran before it.
  3. Spend lots oldest-expiry first, record which lots were used, write one
     debit ledger entry, commit. All in one transaction.
The CHECK (remaining >= 0) constraint is the last line of defence.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import EntryType
from app.exceptions import (
    DriverNotFoundException,
    IdempotencyConflictException,
    InsufficientBalanceException,
)
from app.models import CreditLot, Driver, LedgerEntry, LotConsumption, Redemption
from app.schemas.redemptions import ConsumedLot, RedeemRequest, RedemptionResource
from app.services.credit_policy import format_credits, to_milli
from app.services.driver_service import available_balance


def redeem(
    db: Session, driver_id: str, data: RedeemRequest, idempotency_key: str | None = None
) -> tuple[RedemptionResource, bool]:
    """Returns (redemption, created). created=False = idempotent replay.

    idempotency_key (from the Idempotency-Key header) is optional. Without it a
    retried request is a new redemption — the server cannot tell a retry from a
    genuine second redeem. Concurrency safety never depends on it."""
    amount = to_milli(data.amount)

    with db.begin():
        # 1. lock the driver — serialises every redeem for this driver
        locked = db.scalar(select(Driver.id).where(Driver.id == driver_id).with_for_update())
        if locked is None:
            raise DriverNotFoundException(driver_id)

        # Replay of a redeem we already did? Return it instead of spending again.
        if idempotency_key:
            previous = db.scalar(
                select(Redemption).where(
                    Redemption.driver_id == driver_id,
                    Redemption.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if previous.amount != amount:
                    raise IdempotencyConflictException(idempotency_key)
                return _to_resource(db, previous), False

        # 2. read spendable lots, oldest expiry first
        lots = db.scalars(
            select(CreditLot)
            .where(
                CreditLot.driver_id == driver_id,
                CreditLot.expires_at > func.now(),
                CreditLot.remaining > 0,
            )
            .order_by(CreditLot.expires_at, CreditLot.id)
        ).all()

        available = sum(lot.remaining for lot in lots)
        if available < amount:
            raise InsufficientBalanceException(format_credits(available), format_credits(amount))

        # 3. spend FIFO
        redemption = Redemption(
            driver_id=driver_id,
            amount=amount,
            reason=data.reason,
            idempotency_key=idempotency_key,
        )
        db.add(redemption)
        db.flush()

        still_needed = amount
        for lot in lots:
            if still_needed == 0:
                break
            take = min(lot.remaining, still_needed)
            lot.remaining -= take
            still_needed -= take
            db.add(LotConsumption(redemption_id=redemption.id, lot_id=lot.id, amount=take))

        reason = f"Redeemed {format_credits(amount)} credits"
        if data.reason:
            reason += f": {data.reason}"
        db.add(
            LedgerEntry(
                driver_id=driver_id,
                entry_type=EntryType.DEBIT.value,
                amount=amount,
                reason=reason,
                redemption_id=redemption.id,
            )
        )
        db.flush()
        return _to_resource(db, redemption), True


def _to_resource(db: Session, redemption: Redemption) -> RedemptionResource:
    consumed = db.execute(
        select(CreditLot.ride_id, LotConsumption.amount, CreditLot.expires_at)
        .join(CreditLot, CreditLot.id == LotConsumption.lot_id)
        .where(LotConsumption.redemption_id == redemption.id)
        .order_by(CreditLot.expires_at, CreditLot.id)
    ).all()
    return RedemptionResource(
        redemption_id=redemption.id,
        driver_id=redemption.driver_id,
        amount=format_credits(redemption.amount),
        reason=redemption.reason,
        balance_after=format_credits(available_balance(db, redemption.driver_id)),
        consumed=[
            ConsumedLot(ride_id=r.ride_id, amount=format_credits(r.amount), expires_at=r.expires_at)
            for r in consumed
        ],
        created_at=redemption.created_at,
    )
