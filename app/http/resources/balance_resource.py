from datetime import datetime

from pydantic import BaseModel


class BalanceResource(BaseModel):
    driver_id: str
    balance: str
    owed: str  # taken from the next credits earned
    next_expiry_at: datetime | None
    next_expiry_amount: str | None
