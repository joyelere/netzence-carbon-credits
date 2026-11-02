from datetime import datetime

from pydantic import BaseModel


class ConsumedRide(BaseModel):
    ride_id: str
    amount: str
    expires_at: datetime


class RedemptionResource(BaseModel):
    redemption_id: int  # id of the debit entry in history
    driver_id: str
    amount: str
    reason: str | None
    balance_after: str
    consumed: list[ConsumedRide]
    created_at: datetime
