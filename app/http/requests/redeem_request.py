from decimal import Decimal

from pydantic import BaseModel, Field


class RedeemRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    reason: str | None = Field(default=None, max_length=255)

    model_config = {"json_schema_extra": {"example": {"amount": "2.000", "reason": "Charging voucher"}}}
