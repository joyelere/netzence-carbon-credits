"""Request/response shapes for /rides — FormRequest + API Resource in one place.

If the body doesn't match, FastAPI returns 422 before our code runs.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field

from app.enums import CancellationStatus, RideStatus, VehicleType
from app.schemas.common import Pagination

Id = Field(min_length=1, max_length=64)


class RideCompletedRequest(BaseModel):
    ride_id: str = Id
    driver_id: str = Id
    # max 3 decimals (metres), no negatives, sane upper bound
    distance_km: Decimal = Field(ge=0, le=10_000, max_digits=8, decimal_places=3)
    vehicle_type: VehicleType
    # must include a timezone, e.g. "2026-01-15T10:30:00Z"
    completed_at: AwareDatetime

    model_config = {
        "json_schema_extra": {
            "example": {
                "ride_id": "ride_001",
                "driver_id": "driver_42",
                "distance_km": 12.5,
                "vehicle_type": "electric",
                "completed_at": "2026-10-01T09:30:00Z",
            }
        }
    }


class RideResource(BaseModel):
    ride_id: str
    driver_id: str
    distance_km: str
    vehicle_type: VehicleType
    status: RideStatus
    credits: str  # e.g. "1.500" — string so JSON never carries a float
    completed_at: datetime
    expires_at: datetime


class RideCancelledRequest(BaseModel):
    ride_id: str = Id
    reason: str | None = Field(default=None, max_length=255)

    model_config = {
        "json_schema_extra": {"example": {"ride_id": "ride_001", "reason": "Refunded to passenger"}}
    }


class CancellationResource(BaseModel):
    ride_id: str
    # applied: credits reversed.
    # pending: completion not seen yet; it will be reversed the moment it arrives.
    status: CancellationStatus
    reason: str | None
    received_at: datetime
    applied_at: datetime | None
    reversed: str            # unspent credits taken back
    already_redeemed: str    # spent before the cancellation; not clawed back


class PendingCancellationResource(BaseModel):
    ride_id: str
    reason: str | None
    received_at: datetime
    waiting_hours: float     # how long we have been waiting for the ride's completion


class PendingCancellationsResource(BaseModel):
    older_than_hours: int
    cancellations: list[PendingCancellationResource]
    pagination: Pagination
