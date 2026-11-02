"""Response shapes for /drivers — like API Resources."""

from datetime import datetime

from pydantic import BaseModel

from app.enums import EntryType


class BalanceResource(BaseModel):
    driver_id: str
    balance: str                    # unexpired credits only, e.g. "2.700"
    next_expiry_at: datetime | None  # when the oldest unexpired credits run out
    next_expiry_amount: str | None   # how many credits expire at that time


class HistoryEntryResource(BaseModel):
    id: int | None          # None for computed expiry lines
    type: EntryType
    amount: str             # signed: "+1.500", "-0.700"
    reason: str
    ride_id: str | None
    redemption_id: int | None
    occurred_at: datetime   # when it happened (credits: the ride's completed_at)
    recorded_at: datetime   # when this service recorded it


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
