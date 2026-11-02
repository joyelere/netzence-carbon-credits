from datetime import datetime

from pydantic import BaseModel


class BalanceResource(BaseModel):
    driver_id: str
    balance: str
    next_expiry_at: datetime | None
    next_expiry_amount: str | None
