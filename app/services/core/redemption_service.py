"""Redemptions.

The driver row is locked before the balance is read, so concurrent redeems for
one driver run one after another and can't overspend. Credits are taken from
the rides that expire soonest. The debit ledger entry is the redemption record.
"""

import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import EntryType
from app.exceptions import (
    DriverNotFoundException,
    IdempotencyConflictException,
    InsufficientBalanceException,
)
from app.models import Driver, LedgerEntry, RedemptionAllocation, Ride
from app.http.requests import RedeemRequest
from app.http.resources import ConsumedRide, RedemptionResource
from app.services.calculation.credits import format_credits, to_milli
from app.services.core.driver_service import available_balance


def redeem(
    db: Session, driver_id: str, data: RedeemRequest, idempotency_key: str | None = None
) -> tuple[RedemptionResource, bool]:
    """Returns (redemption, created); created is False for a replayed retry.

    Without an idempotency key a retry counts as a new redemption, since the
    server can't tell it apart from a genuine second one."""
    amount = to_milli(data.amount)

    with db.begin():
        # concurrent redeems for this driver wait here
        locked = db.scalar(select(Driver.id).where(Driver.id == driver_id).with_for_update())
        if locked is None:
            raise DriverNotFoundException(driver_id)

        # same key + same body: return the earlier result instead of spending again
        request_hash = fingerprint(amount, data.reason) if idempotency_key else None
        if idempotency_key:
            previous = db.scalar(
                select(LedgerEntry).where(
                    LedgerEntry.driver_id == driver_id,
                    LedgerEntry.idempotency_key == idempotency_key,
                )
            )
            if previous is not None:
                if previous.request_hash != request_hash:
                    raise IdempotencyConflictException(idempotency_key)
                return _to_resource(db, previous), False

        # spendable rides, soonest expiry first
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
            request_hash=request_hash,
        )
        db.add(debit)
        db.flush()  # need debit.id
        db.add_all(
            RedemptionAllocation(ledger_entry_id=debit.id, ride_id=ride_id, amount=take)
            for ride_id, take in taken
        )
        db.flush()
        return _to_resource(db, debit), True


def fingerprint(amount_milli: int, reason: str | None) -> str:
    """SHA-256 of the normalised body, so "2" and "2.000" hash the same."""
    canonical = json.dumps({"amount": amount_milli, "reason": reason}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


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
