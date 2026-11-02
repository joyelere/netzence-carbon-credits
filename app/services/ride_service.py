"""Business logic for ride events — like app/Services/*Service.php.

Every public function runs in ONE database transaction: either everything is
saved or nothing is (crash halfway = automatic rollback).
"""

import logging

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.enums import CancellationStatus, EntryType, RideStatus
from app.exceptions import RideConflictException
from app.models import Driver, LedgerEntry, RedemptionAllocation, Ride, RideCancellation
from app.schemas.common import Pagination
from app.schemas.rides import (
    CancellationResource,
    PendingCancellationResource,
    PendingCancellationsResource,
    RideCancelledRequest,
    RideCompletedRequest,
    RideResource,
)
from app.services.credit_policy import calculate_credits_milli, expiry_for, format_credits

log = logging.getLogger("app.rides")


def lock_ride_id(db: Session, ride_id: str) -> None:
    """Serialise all events for one ride_id (completed vs cancelled racing),
    even before any row for that ride exists. Released at commit/rollback."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"ride:{ride_id}"})


def lock_driver(db: Session, driver_id: str) -> None:
    """Create the driver row if new, then lock it (SELECT ... FOR UPDATE).
    Every write that touches a driver's credits takes this lock first, so
    they happen one at a time per driver (same idea as lockForUpdate())."""
    db.execute(pg_insert(Driver).values(id=driver_id).on_conflict_do_nothing(index_elements=["id"]))
    db.execute(select(Driver.id).where(Driver.id == driver_id).with_for_update())


def record_completed_ride(db: Session, data: RideCompletedRequest) -> tuple[RideResource, bool]:
    """Returns (ride, created). created=False means it was a duplicate event."""
    with db.begin():
        lock_ride_id(db, data.ride_id)

        existing = db.get(Ride, data.ride_id)
        if existing is not None:
            _ensure_same_event(existing, data)
            return _to_resource(existing), False

        lock_driver(db, data.driver_id)
        credits = calculate_credits_milli(data.distance_km, data.vehicle_type)

        # ON CONFLICT DO NOTHING is the database-level guarantee; the advisory
        # lock above means we normally never reach a conflict here.
        inserted = db.execute(
            pg_insert(Ride)
            .values(
                ride_id=data.ride_id,
                driver_id=data.driver_id,
                distance_km=data.distance_km,
                vehicle_type=data.vehicle_type.value,
                completed_at=data.completed_at,
                credits=credits,
                credits_remaining=credits,
                expires_at=expiry_for(data.completed_at),
                status=RideStatus.COMPLETED.value,
            )
            .on_conflict_do_nothing(index_elements=["ride_id"])
            .returning(Ride.ride_id)
        ).scalar_one_or_none()
        if inserted is None:  # pragma: no cover - guarded by the advisory lock
            return _to_resource(db.get(Ride, data.ride_id)), False

        if credits > 0:
            db.add(
                LedgerEntry(
                    driver_id=data.driver_id,
                    entry_type=EntryType.CREDIT.value,
                    amount=credits,
                    reason=f"Ride {data.ride_id} completed ({data.distance_km} km, {data.vehicle_type.value})",
                    ride_id=data.ride_id,
                )
            )
            db.flush()

        ride = db.get(Ride, data.ride_id)

        # The cancellation arrived first: record the credit (history keeps the
        # original entry) and reverse it straight away in the same transaction.
        early_cancel = db.get(RideCancellation, data.ride_id)
        if early_cancel is not None:
            _apply_reversal(db, ride, early_cancel)

        return _to_resource(ride), True


def record_cancellation(db: Session, data: RideCancelledRequest) -> tuple[CancellationResource, bool]:
    """Returns (cancellation, created). created=False means a duplicate event."""
    with db.begin():
        lock_ride_id(db, data.ride_id)

        previous = db.get(RideCancellation, data.ride_id)
        if previous is not None:
            return _cancellation_resource(db, previous), False

        cancellation = RideCancellation(ride_id=data.ride_id, reason=data.reason)
        db.add(cancellation)
        db.flush()

        driver_id = db.scalar(select(Ride.driver_id).where(Ride.ride_id == data.ride_id))
        if driver_id is not None:
            lock_driver(db, driver_id)
            # Read the ride only AFTER the driver lock, and bypass the session
            # cache: a redeem may have spent some of its credits while we waited.
            ride = db.scalars(
                select(Ride)
                .where(Ride.ride_id == data.ride_id)
                .execution_options(populate_existing=True)
            ).one()
            _apply_reversal(db, ride, cancellation)
        else:
            log.warning(
                "Cancellation for unknown ride %s stored as pending; it will be applied "
                "if the ride's completion arrives.",
                data.ride_id,
            )

        return _cancellation_resource(db, cancellation), True


def _apply_reversal(db: Session, ride: Ride, cancellation: RideCancellation) -> None:
    """Mark the ride cancelled and take back its UNSPENT credits.

    The original credit entry is never touched; a new 'reversal' entry is added.
    Credits already redeemed are not clawed back (that would push the balance
    below zero); they are reported as already_redeemed instead.
    Caller must hold the ride and driver locks.
    """
    ride.status = RideStatus.CANCELLED.value
    # When the cancellation arrived — which may be before the completion did.
    ride.cancelled_at = cancellation.received_at
    reason = cancellation.reason
    cancellation.status = CancellationStatus.APPLIED.value
    cancellation.applied_at = func.now()

    if ride.credits_remaining > 0:
        taken_back = ride.credits_remaining
        ride.credits_remaining = 0
        text_reason = f"Ride {ride.ride_id} cancelled" + (f": {reason}" if reason else "")
        db.add(
            LedgerEntry(
                driver_id=ride.driver_id,
                entry_type=EntryType.REVERSAL.value,
                amount=taken_back,
                reason=text_reason,
                ride_id=ride.ride_id,
            )
        )
    db.flush()


def _cancellation_resource(db: Session, cancellation: RideCancellation) -> CancellationResource:
    db.flush()
    db.refresh(cancellation)  # load DB-set values (received_at, applied_at)
    ride_id = cancellation.ride_id
    reversed_milli = db.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
            LedgerEntry.ride_id == ride_id, LedgerEntry.entry_type == EntryType.REVERSAL.value
        )
    )
    redeemed_milli = db.scalar(
        select(func.coalesce(func.sum(RedemptionAllocation.amount), 0)).where(
            RedemptionAllocation.ride_id == ride_id
        )
    )
    return CancellationResource(
        ride_id=ride_id,
        status=cancellation.status,
        reason=cancellation.reason,
        received_at=cancellation.received_at,
        applied_at=cancellation.applied_at,
        reversed=format_credits(reversed_milli),
        already_redeemed=format_credits(redeemed_milli),
    )


def list_pending_cancellations(
    db: Session, older_than_hours: int, page: int, per_page: int
) -> PendingCancellationsResource:
    """Cancellations still waiting for their ride, received more than
    `older_than_hours` ago. Computed on read, like expiry: no scheduled job.
    A long wait usually means the ride never completed and the ride service
    sent a cancellation it should not have."""
    where = (
        RideCancellation.status == CancellationStatus.PENDING.value,
        RideCancellation.received_at <= func.now() - func.make_interval(0, 0, 0, 0, older_than_hours),
    )
    total = db.scalar(select(func.count()).select_from(RideCancellation).where(*where))
    waiting = func.extract("epoch", func.now() - RideCancellation.received_at) / 3600
    rows = db.execute(
        select(RideCancellation.ride_id, RideCancellation.reason, RideCancellation.received_at, waiting)
        .where(*where)
        .order_by(RideCancellation.received_at)
        .limit(per_page)
        .offset((page - 1) * per_page)
    ).all()
    return PendingCancellationsResource(
        older_than_hours=older_than_hours,
        cancellations=[
            PendingCancellationResource(
                ride_id=r[0], reason=r[1], received_at=r[2], waiting_hours=round(float(r[3]), 1)
            )
            for r in rows
        ],
        pagination=Pagination.build(page, per_page, total),
    )


def _ensure_same_event(existing: Ride, data: RideCompletedRequest) -> None:
    """A true retry carries the same payload. Same ride_id with different data
    is a bug upstream — refuse it loudly instead of silently ignoring it."""
    same = (
        existing.driver_id == data.driver_id
        and existing.distance_km == data.distance_km
        and existing.vehicle_type == data.vehicle_type.value
        and existing.completed_at == data.completed_at
    )
    if not same:
        raise RideConflictException(data.ride_id)


def _to_resource(ride: Ride) -> RideResource:
    return RideResource(
        ride_id=ride.ride_id,
        driver_id=ride.driver_id,
        distance_km=str(ride.distance_km),
        vehicle_type=ride.vehicle_type,
        status=ride.status,
        credits=format_credits(ride.credits),
        completed_at=ride.completed_at,
        expires_at=ride.expires_at,
    )
