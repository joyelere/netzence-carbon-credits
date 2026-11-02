from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import EntryType
from app.models import CreditAllocation, LedgerEntry, Ride


def spendable_rides(db: Session, driver_id: str) -> list[Ride]:
    """Unexpired rides with credits left, soonest expiry first. Caller holds the driver lock."""
    db.flush()  # pending changes to credits_remaining must be visible to the query
    return list(
        db.scalars(
            select(Ride)
            .where(
                Ride.driver_id == driver_id,
                Ride.expires_at > func.now(),
                Ride.credits_remaining > 0,
            )
            .order_by(Ride.expires_at, Ride.ride_id)
        )
    )


def take_credits(
    db: Session,
    rides: list[Ride],
    amount: int,
    *,
    driver_id: str,
    entry_type: EntryType,
    reason: str,
    ride_id: str | None = None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> tuple[LedgerEntry | None, int]:
    """Take up to `amount` from `rides` in order and record it as one ledger entry,
    with an allocation row per ride. Returns (entry, amount taken)."""
    taken: list[tuple[str, int]] = []
    still_needed = amount
    for ride in rides:
        if still_needed == 0:
            break
        take = min(ride.credits_remaining, still_needed)
        if take == 0:
            continue
        ride.credits_remaining -= take
        still_needed -= take
        taken.append((ride.ride_id, take))

    total = amount - still_needed
    if total == 0:
        return None, 0

    entry = LedgerEntry(
        driver_id=driver_id,
        entry_type=entry_type.value,
        amount=total,
        reason=reason,
        ride_id=ride_id,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    db.add(entry)
    db.flush()  # need entry.id
    db.add_all(CreditAllocation(ledger_entry_id=entry.id, ride_id=rid, amount=take) for rid, take in taken)
    db.flush()
    return entry, total
