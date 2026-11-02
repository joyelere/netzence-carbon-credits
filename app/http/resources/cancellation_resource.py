from datetime import datetime

from pydantic import BaseModel

from app.enums import CancellationStatus


class CancellationResource(BaseModel):
    ride_id: str
    status: CancellationStatus
    reason: str | None
    received_at: datetime
    applied_at: datetime | None
    reversed: str
    already_redeemed: str  # spent before the cancellation, not clawed back
