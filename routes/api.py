"""All API routes."""

from fastapi import APIRouter

from app.http.controllers import driver_controller, ride_controller

router = APIRouter()


def get(path, action, **options):
    router.add_api_route(path, action, methods=["GET"], **options)


def post(path, action, **options):
    router.add_api_route(path, action, methods=["POST"], **options)


# Rides (called by the ride service)
post(
    "/rides/completed", ride_controller.completed,
    tags=["Rides"], summary="Record a completed ride and award credits",
    responses={
        201: {"description": "Ride recorded, credits awarded"},
        200: {"description": "Duplicate event: already recorded, nothing changed"},
        409: {"description": "Same ride_id already recorded with different details"},
        422: {"description": "Validation failed"},
    },
)
post(
    "/rides/cancelled", ride_controller.cancelled,
    tags=["Rides"], summary="Reverse a ride's credits (refunded/cancelled after completion)",
    responses={
        200: {"description": "Reversed, or duplicate event: already processed"},
        202: {"description": "Ride not completed yet: stored as pending, reversed when it arrives"},
        422: {"description": "Validation failed"},
    },
)
get(
    "/rides/cancellations/pending", ride_controller.pending_cancellations,
    tags=["Rides"], summary="Cancellations still waiting for their ride's completion",
)

# Drivers
not_found = {404: {"description": "Driver has no recorded rides"}}

get(
    "/drivers/{driver_id}/balance", driver_controller.balance,
    tags=["Drivers"], summary="Current balance (unexpired credits only)", responses=not_found,
)
get(
    "/drivers/{driver_id}/history", driver_controller.history,
    tags=["Drivers"], summary="Every credit and debit with its reason", responses=not_found,
)
post(
    "/drivers/{driver_id}/redeem", driver_controller.redeem,
    tags=["Drivers"], summary="Spend credits (oldest expiry first)",
    responses={
        201: {"description": "Redeemed"},
        200: {"description": "Idempotent replay: this redemption already happened"},
        **not_found,
        409: {"description": "Idempotency-Key reused with a different request body"},
        422: {"description": "Insufficient balance, or validation failed"},
    },
)
