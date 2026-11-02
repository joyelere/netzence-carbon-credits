"""Balance and history.

Expiry is checked at read time against Postgres now(), so nothing needs to run
on a schedule.
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.enums import CreditStatus, EntryType, RideStatus
from app.exceptions import DriverNotFoundException
from app.models import Driver, Ride
from app.http.resources import BalanceResource, HistoryEntryResource, HistoryResource, PaginationResource
from app.services.calculation.credits import format_credits


def ensure_driver_exists(db: Session, driver_id: str) -> None:
    if db.get(Driver, driver_id) is None:
        raise DriverNotFoundException(driver_id)


def available_balance(db: Session, driver_id: str) -> int:
    """Sum of unspent, unexpired credits, in milli-credits."""
    return db.scalar(
        select(func.coalesce(func.sum(Ride.credits_remaining), 0)).where(
            Ride.driver_id == driver_id,
            Ride.status == RideStatus.COMPLETED.value,
            Ride.expires_at > func.now(),
        )
    )


def get_balance(db: Session, driver_id: str) -> BalanceResource:
    driver = db.get(Driver, driver_id)
    if driver is None:
        raise DriverNotFoundException(driver_id)
    balance = available_balance(db, driver_id)

    next_expiry = db.execute(
        select(Ride.expires_at, func.sum(Ride.credits_remaining))
        .where(
            Ride.driver_id == driver_id,
            Ride.status == RideStatus.COMPLETED.value,
            Ride.expires_at > func.now(),
            Ride.credits_remaining > 0,
        )
        .group_by(Ride.expires_at)
        .order_by(Ride.expires_at)
        .limit(1)
    ).first()

    return BalanceResource(
        driver_id=driver_id,
        balance=format_credits(balance),
        owed=format_credits(driver.credits_owed),
        next_expiry_at=next_expiry[0] if next_expiry else None,
        next_expiry_amount=format_credits(next_expiry[1]) if next_expiry else None,
    )


# Credit lines are dated by the ride's completed_at and carry the ride's current
# state, so each adds up: amount = used + recovered + expired + reversed + remaining.
HISTORY_ROWS = """
    SELECT le.id, le.entry_type, le.amount, le.reason, le.ride_id,
           CASE WHEN le.entry_type = 'credit' THEN r.completed_at ELSE le.created_at END AS occurred_at,
           le.created_at AS recorded_at,
           r.credits_remaining, r.expires_at, r.status AS ride_status,
           (SELECT coalesce(sum(a.amount), 0) FROM credit_allocations a
              JOIN ledger_entries x ON x.id = a.ledger_entry_id
             WHERE a.ride_id = r.ride_id AND x.entry_type = 'debit') AS ride_used,
           (SELECT coalesce(sum(a.amount), 0) FROM credit_allocations a
              JOIN ledger_entries x ON x.id = a.ledger_entry_id
             WHERE a.ride_id = r.ride_id AND x.entry_type = 'recovery') AS ride_recovered,
           (SELECT coalesce(sum(rv.amount), 0) FROM ledger_entries rv
             WHERE rv.ride_id = r.ride_id AND rv.entry_type = 'reversal') AS ride_reversed
      FROM ledger_entries le
      LEFT JOIN rides r ON r.ride_id = le.ride_id AND le.entry_type = 'credit'
     WHERE le.driver_id = :driver_id
"""
HISTORY_PAGE_SQL = text(
    f"SELECT * FROM ({HISTORY_ROWS}) h "
    "ORDER BY occurred_at DESC, id DESC LIMIT :limit OFFSET :offset"
)
HISTORY_COUNT_SQL = text(f"SELECT count(*) FROM ({HISTORY_ROWS}) h")


def get_history(db: Session, driver_id: str, page: int, per_page: int) -> HistoryResource:
    ensure_driver_exists(db, driver_id)
    params = {"driver_id": driver_id}
    now = db.scalar(select(func.now()))
    total = db.scalar(HISTORY_COUNT_SQL, params)
    rows = db.execute(
        HISTORY_PAGE_SQL, {**params, "limit": per_page, "offset": (page - 1) * per_page}
    )
    entries = [
        HistoryEntryResource(
            id=r.id,
            type=r.entry_type,
            amount=format_credits(r.amount),
            reason=r.reason,
            ride_id=r.ride_id,
            occurred_at=r.occurred_at,
            recorded_at=r.recorded_at,
            **_credit_state(r, now),
        )
        for r in rows
    ]
    return HistoryResource(
        driver_id=driver_id,
        balance=format_credits(available_balance(db, driver_id)),
        entries=entries,
        pagination=PaginationResource.build(page, per_page, total),
    )


def _credit_state(r, now) -> dict:
    if r.entry_type != EntryType.CREDIT.value or r.expires_at is None:
        return {}
    is_expired = r.expires_at <= now
    spendable = 0 if is_expired else r.credits_remaining
    expired_amount = r.credits_remaining if is_expired else 0
    if r.ride_status == RideStatus.CANCELLED.value:
        status = CreditStatus.REVERSED
    elif is_expired and r.credits_remaining > 0:
        status = CreditStatus.EXPIRED
    elif r.credits_remaining == 0:
        status = CreditStatus.USED
    elif r.ride_used + r.ride_recovered > 0:
        status = CreditStatus.PARTIALLY_USED
    else:
        status = CreditStatus.ACTIVE
    return {
        "status": status,
        "expires_at": r.expires_at,
        "used": format_credits(r.ride_used),
        "recovered": format_credits(r.ride_recovered),
        "expired": format_credits(expired_amount),
        "reversed": format_credits(r.ride_reversed),
        "remaining": format_credits(spendable),
    }
