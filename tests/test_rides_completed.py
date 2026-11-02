"""POST /rides/completed: credit award and duplicate events (requirements 1 & 2)."""

import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import balance, complete, days_ago, scalar


def test_electric_ride_awards_credits_that_expire_12_months_later(client):
    res = complete(client, "r1", km=12.5, completed_at="2026-10-01T09:30:00Z")

    assert res.status_code == 201
    data = res.json()["data"]
    assert data["credits"] == "1.500"
    assert data["expires_at"] == "2027-10-01T09:30:00Z"
    assert balance(client) == "1.500"


def test_non_electric_ride_is_recorded_with_zero_credits(client):
    res = complete(client, "r1", vehicle="petrol", km=30)

    assert res.status_code == 201
    assert res.json()["data"]["credits"] == "0.000"
    assert scalar("SELECT count(*) FROM rides") == 1
    assert scalar("SELECT count(*) FROM ledger_entries") == 0


def test_same_event_twice_adds_credits_once(client):
    first = complete(client, "r1", km=10)
    second = complete(client, "r1", km=10, completed_at=first.json()["data"]["completed_at"])

    assert first.status_code == 201
    assert second.status_code == 200
    assert balance(client) == "1.200"
    assert scalar("SELECT count(*) FROM rides") == 1
    assert scalar("SELECT count(*) FROM ledger_entries") == 1


def test_same_ride_id_with_different_details_is_rejected(client):
    complete(client, "r1", km=10, completed_at="2026-10-01T09:30:00Z")
    res = complete(client, "r1", km=99, completed_at="2026-10-01T09:30:00Z")

    assert res.status_code == 409
    assert balance(client) == "1.200"


def test_duplicate_events_arriving_at_the_same_time_credit_once():
    """10 copies of one event, released at the same instant from 10 threads."""
    n = 10
    start = threading.Barrier(n)
    completed_at = days_ago(1)

    def send(_):
        start.wait()
        return complete(TestClient(app), "r1", km=10, completed_at=completed_at).status_code

    with ThreadPoolExecutor(n) as pool:
        codes = sorted(pool.map(send, range(n)))

    assert codes.count(201) == 1
    assert codes.count(200) == n - 1
    assert scalar("SELECT count(*) FROM rides") == 1
    assert scalar("SELECT sum(amount) FROM ledger_entries") == 1200


def test_invalid_payload_is_rejected(client):
    res = client.post(
        "/rides/completed",
        json={
            "ride_id": "r1",
            "driver_id": "d1",
            "distance_km": -5,
            "vehicle_type": "bicycle",
            "completed_at": "2026-10-01T09:30:00",  # no timezone
        },
    )

    assert res.status_code == 422
    bad_fields = {e["loc"][-1] for e in res.json()["errors"]}
    assert bad_fields == {"distance_km", "vehicle_type", "completed_at"}
