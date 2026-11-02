"""Read side: balance and history.

Expiry is computed at read time — no cron job. A lot counts toward the balance
only while expires_at > now(). Postgres's now() is the single clock used.
"""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.enums import CreditStatus, EntryType, RideStatus
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


# History = the stored ledger (credits, debits, reversals), newest first.
# Credit lines also carry their lot's live state (status, used, expired,
# reversed, remaining) so each one explains itself:
# amount = used + expired + reversed + remaining
# Credits are dated by when the ride was completed (lot.earned_at), not when
# we happened to receive the event, so the timeline reads in real-world order.
HISTORY_ROWS = """
    SELECT le.id, le.entry_type, le.amount, le.reason, le.ride_id, le.redemption_id,
           CASE WHEN le.entry_type = 'credit' THEN cl.earned_at ELSE le.created_at END AS occurred_at,
           le.created_at AS recorded_at,
           cl.amount AS lot_amount, cl.remaining AS lot_remaining, cl.expires_at,
           (SELECT coalesce(sum(lc.amount), 0) FROM lot_consumptions lc WHERE lc.lot_id = cl.id) AS lot_used,
           (SELECT coalesce(sum(rv.amount), 0) FROM ledger_entries rv
             WHERE rv.lot_id = cl.id AND rv.entry_type = 'reversal') AS lot_reversed,
           r.status AS ride_status
      FROM ledger_entries le
      LEFT JOIN credit_lots cl ON cl.id = le.lot_id AND le.entry_type = 'credit'
      LEFT JOIN rides r ON r.ride_id = cl.ride_id
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
            redemption_id=r.redemption_id,
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
        pagination=Pagination(
            current_page=page,
            per_page=per_page,
            total=total,
            last_page=max(1, -(-total // per_page)),  # ceil division
        ),
    )


def _credit_state(r, now) -> dict:
    """Status of a credit line's lot, worked out from its current numbers."""
    if r.entry_type != EntryType.CREDIT.value or r.lot_amount is None:
        return {}
    is_expired = r.expires_at <= now
    spendable = 0 if is_expired else r.lot_remaining
    expired_amount = r.lot_remaining if is_expired else 0
    if r.ride_status == RideStatus.CANCELLED.value:
        status = CreditStatus.REVERSED
    elif is_expired and r.lot_remaining > 0:
        status = CreditStatus.EXPIRED
    elif r.lot_remaining == 0:
        status = CreditStatus.USED
    elif r.lot_used > 0:
        status = CreditStatus.PARTIALLY_USED
    else:
        status = CreditStatus.ACTIVE
    return {
        "status": status,
        "expires_at": r.expires_at,
        "used": format_credits(r.lot_used),
        "expired": format_credits(expired_amount),
        "reversed": format_credits(r.lot_reversed),
        "remaining": format_credits(spendable),
    }
