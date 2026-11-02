from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CreditAllocation(Base):
    """How much a debit (redemption) or recovery entry took from each ride."""

    __tablename__ = "credit_allocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ledger_entry_id: Mapped[int] = mapped_column(ForeignKey("ledger_entries.id"))
    ride_id: Mapped[str] = mapped_column(ForeignKey("rides.ride_id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
