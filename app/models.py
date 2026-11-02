"""SQLAlchemy models — the Python version of app/Models/*.

All credit amounts are BIGINT **milli-credits** (1 credit = 1000) so money math
is integer-only and can never produce rounding errors.

The schema itself is created by Alembic migrations (alembic/versions), not by
these classes; they only describe the tables so Python can query them.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Driver(Base):
    """One row per driver. Redemptions lock this row (SELECT ... FOR UPDATE)."""

    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ride(Base):
    """Every completed-ride event we accepted. ride_id is the primary key, so the
    same event can only ever be stored once (idempotency enforced by Postgres)."""

    __tablename__ = "rides"

    ride_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    vehicle_type: Mapped[str] = mapped_column(String(16))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    credits: Mapped[int] = mapped_column(BigInteger)  # milli-credits awarded
    status: Mapped[str] = mapped_column(String(16))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RideCancellation(Base):
    """Every cancellation event we received — including ones that arrive BEFORE
    the completion event. When the completion later arrives, it sees this row
    and is recorded-then-reversed immediately."""

    __tablename__ = "ride_cancellations"

    ride_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CreditLot(Base):
    """A batch of credits from one ride. `remaining` goes down as it is redeemed
    (oldest expires_at first). Balance = SUM(remaining) WHERE expires_at > now()."""

    __tablename__ = "credit_lots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    ride_id: Mapped[str] = mapped_column(ForeignKey("rides.ride_id"), unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    remaining: Mapped[int] = mapped_column(BigInteger)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Redemption(Base):
    """One redeem request. idempotency_key (optional) makes client retries safe."""

    __tablename__ = "redemptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LotConsumption(Base):
    """How much of which lot a redemption used — the audit trail for FIFO."""

    __tablename__ = "lot_consumptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    redemption_id: Mapped[int] = mapped_column(ForeignKey("redemptions.id"))
    lot_id: Mapped[int] = mapped_column(ForeignKey("credit_lots.id"))
    amount: Mapped[int] = mapped_column(BigInteger)


class LedgerEntry(Base):
    """Append-only history. Never UPDATEd or DELETEd: corrections are new rows.
    amount is always positive; entry_type says whether it adds or subtracts."""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    entry_type: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    ride_id: Mapped[str | None] = mapped_column(ForeignKey("rides.ride_id"))
    redemption_id: Mapped[int | None] = mapped_column(ForeignKey("redemptions.id"))
    lot_id: Mapped[int | None] = mapped_column(ForeignKey("credit_lots.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
