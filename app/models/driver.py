from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Driver(Base):
    """Locked (FOR UPDATE) by every write to the driver's credits."""

    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # used credits of cancelled rides not yet recovered; taken from the next credits earned
    credits_owed: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
