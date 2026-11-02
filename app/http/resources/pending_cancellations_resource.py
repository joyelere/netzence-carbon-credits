from datetime import datetime

from pydantic import BaseModel

from app.http.resources.pagination_resource import PaginationResource


class PendingCancellationResource(BaseModel):
    ride_id: str
    reason: str | None
    received_at: datetime
    waiting_hours: float


class PendingCancellationsResource(BaseModel):
    older_than_hours: int
    cancellations: list[PendingCancellationResource]
    pagination: PaginationResource
