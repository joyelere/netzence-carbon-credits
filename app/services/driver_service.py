"""Read side: balance and history.

Expiry is computed at read time — no cron job. A lot counts toward the balance
only while expires_at > now(). Postgres's now() is the single clock used.
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.exceptions import DriverNotFoundException
from app.models import CreditLot, Driver
from app.schemas.drivers import BalanceResource, HistoryEntryResource, HistoryResource, Pagination
from app.services.credit_policy import format_credits


def ensure_driver_exists(db: Session, driver_id: str) -> None:
    if db.get(Driver, driver_id) is None:
        raise DriverNotFoundException(driver_id)


def available_balance(db: Session, driver_id: str) -> int:
    """Sum of unspent, unexpired credits, in milli-credits."""
    return db.scalar(
        select(func.coalesce(func.sum(CreditLot.remaining), 0)).where(
            CreditLot.driver_id == driver_id,
            CreditLot.expires_at > func.now(),
        )
    )


def get_balance(db: Session, driver_id: str) -> BalanceResource:
    ensure_driver_exists(db, driver_id)
    balance = available_balance(db, driver_id)

    next_lot = db.execute(
        select(CreditLot.expires_at, func.sum(CreditLot.remaining))
        .where(
            CreditLot.driver_id == driver_id,
            CreditLot.expires_at > func.now(),
            CreditLot.remaining > 0,
        )
        .group_by(CreditLot.expires_at)
        .order_by(CreditLot.expires_at)
        .limit(1)
    ).first()

    return BalanceResource(
        driver_id=driver_id,
        balance=format_credits(balance),
        next_expiry_at=next_lot[0] if next_lot else None,
        next_expiry_amount=format_credits(next_lot[1]) if next_lot else None,
    )


# Stored ledger rows + one computed "expiry" row per lot that expired unused.
# Summing every row of a driver's history always equals their balance.
# Credits are dated by when the ride was completed (lot.earned_at), not when
# we happened to receive the event, so the timeline reads in real-world order.
HISTORY_ROWS = """
    SELECT le.id, le.entry_type, le.amount, le.reason, le.ride_id, le.redemption_id,
           CASE WHEN le.entry_type = 'credit' THEN cl.earned_at ELSE le.created_at END AS occurred_at,
           le.created_at AS recorded_at
      FROM ledger_entries le
      LEFT JOIN credit_lots cl ON cl.id = le.lot_id
     WHERE le.driver_id = :driver_id
    UNION ALL
    SELECT NULL, 'expiry', -remaining,
           'Unused credits from ride ' || ride_id || ' expired on '
               || to_char(expires_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')
               || ' (12 months after the ride)',
           ride_id, NULL, expires_at, expires_at
      FROM credit_lots
     WHERE driver_id = :driver_id AND expires_at <= now() AND remaining > 0
"""
HISTORY_PAGE_SQL = text(
    f"SELECT * FROM ({HISTORY_ROWS}) h "
    "ORDER BY occurred_at DESC, id DESC NULLS FIRST LIMIT :limit OFFSET :offset"
)
HISTORY_COUNT_SQL = text(f"SELECT count(*) FROM ({HISTORY_ROWS}) h")


def get_history(db: Session, driver_id: str, page: int, per_page: int) -> HistoryResource:
    ensure_driver_exists(db, driver_id)
    params = {"driver_id": driver_id}
    total = db.scalar(HISTORY_COUNT_SQL, params)
    rows = db.execute(
        HISTORY_PAGE_SQL, {**params, "limit": per_page, "offset": (page - 1) * per_page}
    )
    entries = [
        HistoryEntryResource(
            id=r.id,
            type=r.entry_type,
            amount=("+" if r.amount > 0 else "") + format_credits(r.amount),
            reason=r.reason,
            ride_id=r.ride_id,
            redemption_id=r.redemption_id,
            occurred_at=r.occurred_at,
            recorded_at=r.recorded_at,
        )
        for r in rows
    ]
    return HistoryResource(
        driver_id=driver_id,
        balance=format_credits(available_balance(db, driver_id)),
        entries=entries,
        pagination=Pagination(
            current_page=page,
            per_page=per_page,
            total=total,
            last_page=max(1, -(-total // per_page)),  # ceil division
        ),
    )
