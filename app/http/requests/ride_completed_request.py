from decimal import Decimal

from pydantic import AwareDatetime, BaseModel, Field

from app.enums import VehicleType


class RideCompletedRequest(BaseModel):
    ride_id: str = Field(min_length=1, max_length=64)
    driver_id: str = Field(min_length=1, max_length=64)
    distance_km: Decimal = Field(ge=0, le=10_000, max_digits=8, decimal_places=3)
    vehicle_type: VehicleType
    # timezone required
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
