"""Business logic for ride events — like app/Services/*Service.php.

Every public function runs in ONE database transaction: either everything is
saved or nothing is (crash halfway = automatic rollback).
"""

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.enums import EntryType, RideStatus
from app.exceptions import RideConflictException
from app.models import CreditLot, Driver, LedgerEntry, Ride
from app.schemas.rides import RideCompletedRequest, RideResource
from app.services.credit_policy import calculate_credits_milli, expiry_for, format_credits


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
            return _to_resource(db, existing), False

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
                status=RideStatus.COMPLETED.value,
            )
            .on_conflict_do_nothing(index_elements=["ride_id"])
            .returning(Ride.ride_id)
        ).scalar_one_or_none()
        if inserted is None:  # pragma: no cover - guarded by the advisory lock
            return _to_resource(db, db.get(Ride, data.ride_id)), False

        if credits > 0:
            lot = CreditLot(
                driver_id=data.driver_id,
                ride_id=data.ride_id,
                amount=credits,
                remaining=credits,
                earned_at=data.completed_at,
                expires_at=expiry_for(data.completed_at),
            )
            db.add(lot)
            db.flush()  # get lot.id
            db.add(
                LedgerEntry(
                    driver_id=data.driver_id,
                    entry_type=EntryType.CREDIT.value,
                    amount=credits,
                    reason=f"Ride {data.ride_id} completed ({data.distance_km} km, {data.vehicle_type.value})",
                    ride_id=data.ride_id,
                    lot_id=lot.id,
                )
            )
            db.flush()

        ride = db.get(Ride, data.ride_id)
        return _to_resource(db, ride), True


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


def _to_resource(db: Session, ride: Ride) -> RideResource:
    lot = db.scalar(select(CreditLot).where(CreditLot.ride_id == ride.ride_id))
    return RideResource(
        ride_id=ride.ride_id,
        driver_id=ride.driver_id,
        distance_km=str(ride.distance_km),
        vehicle_type=ride.vehicle_type,
        status=ride.status,
        credits=format_credits(ride.credits),
        completed_at=ride.completed_at,
        expires_at=lot.expires_at if lot else None,
    )
