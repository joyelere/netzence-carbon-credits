"""SQLAlchemy models — the Python version of app/Models/*.

Five tables:
  drivers                 one row per driver; redeem locks it (SELECT ... FOR UPDATE)
  rides                   every ride event + the credits it earned and how many are left
  ledger_entries          append-only history: credit / debit (= a redemption) / reversal
  redemption_allocations  which rides' credits each redemption used (FIFO audit trail)
  ride_cancellations      every cancellation received, including ones that arrive early

All credit amounts are BIGINT **milli-credits** (1 credit = 1000), like kobo.
The schema is created by Alembic migrations (alembic/versions), not by these
classes; they only describe the tables so Python can query them.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Driver(Base):
    """Like the Wallet row you lockForUpdate(): every write to a driver's
    credits locks this row first, so they happen one at a time."""

    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ride(Base):
    """A completed-ride event and the credits it earned.

    ride_id is the primary key, so the same event can only be stored once.
    credits_remaining goes down as the driver redeems (oldest expires_at first)
    and to 0 if the ride is cancelled.
    Balance = SUM(credits_remaining) WHERE expires_at > now().
    """

    __tablename__ = "rides"

    ride_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    distance_km: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    vehicle_type: Mapped[str] = mapped_column(String(16))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    credits: Mapped[int] = mapped_column(BigInteger)            # earned (milli-credits)
    credits_remaining: Mapped[int] = mapped_column(BigInteger)  # still unspent
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RideCancellation(Base):
    """Every cancellation event received — including ones that arrive BEFORE
    the completion. When that completion later arrives it sees this row and is
    recorded-then-reversed in the same transaction."""

    __tablename__ = "ride_cancellations"

    ride_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | applied
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LedgerEntry(Base):
    """Append-only history (UPDATE/DELETE blocked by a DB trigger).

    entry_type: credit (ride earned) | debit (a redemption) | reversal (ride cancelled).
    amount is always positive; entry_type gives the direction.
    idempotency_key: set on debits when the client sent an Idempotency-Key header.
    """

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    entry_type: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    ride_id: Mapped[str | None] = mapped_column(ForeignKey("rides.ride_id"))
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RedemptionAllocation(Base):
    """Redemption (debit entry) X took `amount` from ride Y's credits.
    One redemption can draw on several rides, oldest expiry first."""

    __tablename__ = "redemption_allocations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ledger_entry_id: Mapped[int] = mapped_column(ForeignKey("ledger_entries.id"))
    ride_id: Mapped[str] = mapped_column(ForeignKey("rides.ride_id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
