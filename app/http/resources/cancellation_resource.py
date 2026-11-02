from datetime import datetime

from pydantic import BaseModel

from app.enums import CancellationStatus


class CancellationResource(BaseModel):
    ride_id: str
    status: CancellationStatus
    reason: str | None
    received_at: datetime
    applied_at: datetime | None
    # null while pending
    reversed: str | None   # the ride's own unspent credits
    recovered: str | None  # already-used credits, taken from the driver's other credits
    owed: str | None       # already-used credits the driver couldn't cover yet
