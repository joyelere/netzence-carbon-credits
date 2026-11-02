from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Ride(Base):
    """A completed ride and its credits (milli-credits).

    Balance = sum of credits_remaining on rides that haven't expired.
    """

    __tablename__ = "rides"

    ride_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    vehicle_type: Mapped[str] = mapped_column(String(16))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    credits: Mapped[int] = mapped_column(BigInteger)
    credits_remaining: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
