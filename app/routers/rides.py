"""Ride event endpoints — like a Laravel controller + its routes.

Routers stay thin: validate (done by the schema), call the service, respond.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.responses import send_created, send_success
from app.schemas.rides import RideCompletedRequest
from app.services import ride_service

router = APIRouter(prefix="/rides", tags=["Rides"])


@router.post(
    "/completed",
    summary="Record a completed ride and award credits",
    responses={
        201: {"description": "Ride recorded, credits awarded"},
        200: {"description": "Duplicate event — already recorded, nothing changed"},
        409: {"description": "Same ride_id already recorded with different details"},
        422: {"description": "Validation failed"},
    },
)
def ride_completed(body: RideCompletedRequest, db: Session = Depends(get_db)):
    ride, created = ride_service.record_completed_ride(db, body)
    data = ride.model_dump(mode="json")
    if created:
        return send_created("Ride", data)
    return send_success("Ride already recorded; no credits added.", data)
