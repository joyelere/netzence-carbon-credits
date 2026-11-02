"""Request/response shapes for /rides — FormRequest + API Resource in one place.

If the body doesn't match, FastAPI returns 422 before our code runs.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field

from app.enums import RideStatus, VehicleType

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
    expires_at: datetime | None
