from datetime import datetime

from pydantic import BaseModel

from app.enums import CreditStatus, EntryType
from app.http.resources.pagination_resource import PaginationResource


class HistoryEntryResource(BaseModel):
    id: int
    type: EntryType
    amount: str  # always positive; type gives the direction
    reason: str
    ride_id: str | None
    occurred_at: datetime  # for credits, the ride's completed_at
    recorded_at: datetime
    # credit lines only: amount = used + expired + reversed + remaining
    status: CreditStatus | None = None
    expires_at: datetime | None = None
    used: str | None = None
    expired: str | None = None
    reversed: str | None = None
    remaining: str | None = None


class HistoryResource(BaseModel):
    driver_id: str
    balance: str
    entries: list[HistoryEntryResource]
    pagination: PaginationResource
