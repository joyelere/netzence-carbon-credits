"""Request/response shapes for POST /drivers/{id}/redeem."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class RedeemRequest(BaseModel):
    # > 0, max 3 decimal places (one milli-credit)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    reason: str | None = Field(default=None, max_length=255)

    model_config = {"json_schema_extra": {"example": {"amount": "2.000", "reason": "Charging voucher"}}}


class ConsumedLot(BaseModel):
    ride_id: str
    amount: str
    expires_at: datetime


class RedemptionResource(BaseModel):
    redemption_id: int
    driver_id: str
    amount: str
    reason: str | None
    balance_after: str
    consumed: list[ConsumedLot]  # which rides' credits were used, oldest first
    created_at: datetime
