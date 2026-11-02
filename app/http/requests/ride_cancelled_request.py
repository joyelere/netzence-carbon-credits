from pydantic import BaseModel, Field


class RideCancelledRequest(BaseModel):
    ride_id: str = Field(min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=255)

    model_config = {"json_schema_extra": {"example": {"ride_id": "ride_001", "reason": "Refunded to passenger"}}}
