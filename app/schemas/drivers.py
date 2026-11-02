"""Response shapes for /drivers — like API Resources."""

from datetime import datetime

from pydantic import BaseModel

from app.enums import CreditStatus, EntryType


class BalanceResource(BaseModel):
    driver_id: str
    balance: str                    # unexpired credits only, e.g. "2.700"
    next_expiry_at: datetime | None  # when the oldest unexpired credits run out
    next_expiry_amount: str | None   # how many credits expire at that time


class HistoryEntryResource(BaseModel):
    id: int
    type: EntryType
    amount: str             # always positive, e.g. "1.500"; `type` gives the direction
    reason: str
    ride_id: str | None
    redemption_id: int | None
    occurred_at: datetime         # when it happened (credits: the ride's completed_at)
    recorded_at: datetime         # when this service saved it
    # Credit lines only (null on others): what has happened to these credits so far
    status: CreditStatus | None = None
    expires_at: datetime | None = None
    used: str | None = None        # redeemed from this ride's credits
    expired: str | None = None     # ran out unused at expires_at
    remaining: str | None = None   # still spendable now


class Pagination(BaseModel):
    """Same shape as Laravel's paginate() meta."""

    current_page: int
    per_page: int
    total: int
    last_page: int


class HistoryResource(BaseModel):
    driver_id: str
    balance: str
    entries: list[HistoryEntryResource]
    pagination: Pagination
