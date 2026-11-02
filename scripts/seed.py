"""Reset the dev database and load demo data covering every case.

    make seed

Goes through the same services as the API, so the data is always consistent.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.database import SessionLocal, engine
from app.enums import VehicleType
from app.http.requests import RedeemRequest, RideCancelledRequest, RideCompletedRequest
from app.services.core import redemption_service, ride_service

TABLES = "credit_allocations, ledger_entries, ride_cancellations, rides, drivers"


def days_ago(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def ride(ride_id, driver_id, km, days, vehicle=VehicleType.ELECTRIC):
    with SessionLocal() as db:
        ride_service.record_completed_ride(
            db,
            RideCompletedRequest(
                ride_id=ride_id,
                driver_id=driver_id,
                distance_km=Decimal(str(km)),
                vehicle_type=vehicle,
                completed_at=days_ago(days),
            ),
        )


def redeem(driver_id, amount, reason):
    with SessionLocal() as db:
        redemption_service.redeem(db, driver_id, RedeemRequest(amount=Decimal(amount), reason=reason))


def cancel(ride_id, reason):
    with SessionLocal() as db:
        ride_service.record_cancellation(db, RideCancelledRequest(ride_id=ride_id, reason=reason))


def main() -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))

    # amaka: active, partially used, fully used and expired credits; a petrol ride
    ride("amaka_r1", "amaka", 50, days=400)   # 6.000, expired
    ride("amaka_r2", "amaka", 25, days=60)    # 3.000
    ride("amaka_r3", "amaka", 20, days=30)    # 2.400
    ride("amaka_r4", "amaka", 10, days=5)     # 1.200
    ride("amaka_r5", "amaka", 30, days=3, vehicle=VehicleType.PETROL)  # 0 credits
    redeem("amaka", "4.000", "Charging voucher")  # all of r2, 1.000 of r3

    # tunde: ride refunded after he redeemed from it; owes the rest, repaid by his next ride
    ride("tunde_r1", "tunde", 25, days=20)    # 3.000
    redeem("tunde", "2.000", "Service discount")
    cancel("tunde_r1", "Refunded to passenger")  # reverses 1.000, owes 2.000
    ride("tunde_r2", "tunde", 25, days=2)     # 3.000: 2.000 repays the debt

    # zainab: the cancellation arrived before the ride's completion
    cancel("zainab_r1", "Passenger disputed the trip")
    ride("zainab_r1", "zainab", 10, days=1)   # credited and reversed straight away
    ride("zainab_r2", "zainab", 15, days=1)   # 1.800

    # a cancellation whose ride never arrived, received three days ago
    cancel("ghost_ride", "Sent by mistake")
    with engine.begin() as conn:
        conn.execute(text("UPDATE ride_cancellations SET received_at = now() - interval '3 days' "
                          "WHERE ride_id = 'ghost_ride'"))

    print("Seeded drivers: amaka, tunde, zainab (+ one stuck pending cancellation)")


if __name__ == "__main__":
    main()
