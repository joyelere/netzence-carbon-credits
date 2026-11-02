
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.http.requests import PendingCancellationsRequest, RideCancelledRequest, RideCompletedRequest
from app.services.core import ride_service
from app.traits.responses import send_created, send_fetched, send_success


def completed(body: RideCompletedRequest, db: Session = Depends(get_db)):
    """Idempotent on ride_id. Electric rides earn 0.12 credits/km, valid 12 months."""
    ride, created = ride_service.record_completed_ride(db, body)
    data = ride.model_dump(mode="json")
    if created:
        return send_created("Ride", data)
    return send_success("Ride already recorded; no credits added.", data)


def cancelled(body: RideCancelledRequest, db: Session = Depends(get_db)):
    """Reverses the ride's unspent credits; the original entry stays in history.
    If the ride hasn't arrived yet, the cancellation is kept as pending (202)."""
    cancellation, created = ride_service.record_cancellation(db, body)
    data = cancellation.model_dump(mode="json")
    if not created:
        return send_success("Cancellation already recorded; nothing changed.", data)
    if cancellation.status == "pending":
        return send_success(
            "Cancellation recorded. Ride not completed yet; its credits will be reversed on arrival.",
            data,
            202,
        )
    return send_success("Ride cancelled; unspent credits reversed.", data)


def pending_cancellations(
    query: Annotated[PendingCancellationsRequest, Query()],
    db: Session = Depends(get_db),
):
    """Pending cancellations whose ride still hasn't arrived after `older_than_hours`."""
    data = ride_service.list_pending_cancellations(db, query.older_than_hours, query.page, query.per_page)
    return send_fetched("Pending cancellations", data.model_dump(mode="json"))
