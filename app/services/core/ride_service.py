"""Ride completion and cancellation. Each public function is one transaction."""

import logging

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.enums import CancellationStatus, EntryType, RideStatus
from app.exceptions import RideConflictException
from app.models import Driver, LedgerEntry, Ride, RideCancellation
from app.http.requests import RideCancelledRequest, RideCompletedRequest
from app.http.resources import (
    CancellationResource,
    PaginationResource,
    PendingCancellationResource,
    PendingCancellationsResource,
    RideResource,
)
from app.services.calculation.credits import calculate_credits_milli, expiry_for, format_credits
from app.services.core.credit_spending import spendable_rides, take_credits

log = logging.getLogger("app.rides")


def lock_ride_id(db: Session, ride_id: str) -> None:
    """Serialise events for one ride_id (e.g. a completion and a cancellation
    arriving together), even before the ride row exists."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"ride:{ride_id}"})


def lock_driver(db: Session, driver_id: str) -> Driver:
    """Create the driver row if needed and lock it. Every write to a driver's
    credits takes this lock first."""
    db.execute(pg_insert(Driver).values(id=driver_id).on_conflict_do_nothing(index_elements=["id"]))
    return db.scalars(
        select(Driver).where(Driver.id == driver_id).with_for_update().execution_options(populate_existing=True)
    ).one()


def record_completed_ride(db: Session, data: RideCompletedRequest) -> tuple[RideResource, bool]:
    """Returns (ride, created); created is False for a duplicate event."""
    with db.begin():
        lock_ride_id(db, data.ride_id)

        existing = db.get(Ride, data.ride_id)
        if existing is not None:
            _ensure_same_event(existing, data)
            return _to_resource(existing), False

        driver = lock_driver(db, data.driver_id)
        credits = calculate_credits_milli(data.distance_km, data.vehicle_type)

        # The primary key is the final guard against double credits.
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
        if inserted is None:  # pragma: no cover
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

        # The cancellation got here first: keep the credit entry, reverse it now.
        early_cancel = db.get(RideCancellation, data.ride_id)
        if early_cancel is not None:
            _apply_reversal(db, ride, early_cancel, driver)
        elif driver.credits_owed > 0:
            _recover_owed(db, driver)

        return _to_resource(ride), True


def record_cancellation(db: Session, data: RideCancelledRequest) -> tuple[CancellationResource, bool]:
    """Returns (cancellation, created); created is False for a duplicate event."""
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
            driver = lock_driver(db, driver_id)
            # Re-read after the lock: a redeem may have spent some credits meanwhile.
            ride = db.scalars(
                select(Ride)
                .where(Ride.ride_id == data.ride_id)
                .execution_options(populate_existing=True)
            ).one()
            _apply_reversal(db, ride, cancellation, driver)
        else:
            log.warning(
                "Cancellation for unknown ride %s stored as pending; it will be applied "
                "if the ride's completion arrives.",
                data.ride_id,
            )

        return _cancellation_resource(db, cancellation), True


def _apply_reversal(db: Session, ride: Ride, cancellation: RideCancellation, driver: Driver) -> None:
    """Take back the ride's own unspent credits. Whatever it had already used
    (redeemed, or spent repaying a debt) is taken from the driver's other
    credits; anything they can't cover is added to credits_owed, so the balance
    never goes negative. Caller holds the ride and driver locks."""
    ride.status = RideStatus.CANCELLED.value
    ride.cancelled_at = cancellation.received_at  # can be earlier than the completion
    label = f"Ride {ride.ride_id} cancelled" + (f": {cancellation.reason}" if cancellation.reason else "")

    reversed_ = ride.credits_remaining
    if reversed_ > 0:
        ride.credits_remaining = 0
        db.add(
            LedgerEntry(
                driver_id=ride.driver_id,
                entry_type=EntryType.REVERSAL.value,
                amount=reversed_,
                reason=label,
                ride_id=ride.ride_id,
            )
        )

    already_used = ride.credits - reversed_
    recovered = 0
    if already_used > 0:
        _, recovered = take_credits(
            db,
            spendable_rides(db, ride.driver_id),
            already_used,
            driver_id=ride.driver_id,
            entry_type=EntryType.RECOVERY,
            reason=f"{label} (credits already used, taken from balance)",
            ride_id=ride.ride_id,
        )
    owed = already_used - recovered
    driver.credits_owed += owed
    if owed:
        log.info("Driver %s owes %s credits after ride %s was cancelled", driver.id, format_credits(owed), ride.ride_id)

    cancellation.status = CancellationStatus.APPLIED.value
    cancellation.applied_at = func.now()
    cancellation.reversed_amount = reversed_
    cancellation.recovered_amount = recovered
    cancellation.owed_amount = owed
    db.flush()


def _recover_owed(db: Session, driver: Driver) -> None:
    """Take what the driver owes from their credits, starting with the ones just earned."""
    _, recovered = take_credits(
        db,
        spendable_rides(db, driver.id),
        driver.credits_owed,
        driver_id=driver.id,
        entry_type=EntryType.RECOVERY,
        reason="Credits owed from cancelled rides, taken from new credits",
    )
    driver.credits_owed -= recovered
    db.flush()


def _cancellation_resource(db: Session, cancellation: RideCancellation) -> CancellationResource:
    db.flush()
    db.refresh(cancellation)  # received_at / applied_at are set by the DB
    amount = lambda v: None if v is None else format_credits(v)  # noqa: E731
    return CancellationResource(
        ride_id=cancellation.ride_id,
        status=cancellation.status,
        reason=cancellation.reason,
        received_at=cancellation.received_at,
        applied_at=cancellation.applied_at,
        reversed=amount(cancellation.reversed_amount),
        recovered=amount(cancellation.recovered_amount),
        owed=amount(cancellation.owed_amount),
    )


def list_pending_cancellations(
    db: Session, older_than_hours: int, page: int, per_page: int
) -> PendingCancellationsResource:
    """Pending cancellations older than `older_than_hours`. A long wait usually
    means the ride never completed."""
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
        pagination=PaginationResource.build(page, per_page, total),
    )


def _ensure_same_event(existing: Ride, data: RideCompletedRequest) -> None:
    """Same ride_id with different details is an upstream bug; reject it."""
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
