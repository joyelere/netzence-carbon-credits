from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LedgerEntry(Base):
    """Append-only history; a DB trigger blocks UPDATE and DELETE.
    amount is always positive, entry_type gives the direction."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    entry_type: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    ride_id: Mapped[str | None] = mapped_column(ForeignKey("rides.ride_id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
