"""Tests run against a real Postgres database (TEST_DATABASE_URL).
The schema is built from the migrations once, and tables are emptied before each test."""

import os
from datetime import UTC, datetime, timedelta

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://netzence:netzence@localhost:5433/netzence_test"
)

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402

TABLES = "credit_allocations, ledger_entries, ride_cancellations, rides, drivers"


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    # TRUNCATE bypasses the append-only trigger
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def client():
    return TestClient(app)


# ---------- helpers ---------------------------------------------------------

def days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def complete(client, ride_id, driver_id="d1", km=10, vehicle="electric", completed_at=None):
    return client.post(
        "/rides/completed",
        json={
            "ride_id": ride_id,
            "driver_id": driver_id,
            "distance_km": km,
            "vehicle_type": vehicle,
            "completed_at": completed_at or days_ago(1),
        },
    )


def cancel(client, ride_id, reason="Refunded"):
    return client.post("/rides/cancelled", json={"ride_id": ride_id, "reason": reason})


def redeem(client, amount, driver_id="d1", key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"/drivers/{driver_id}/redeem", json={"amount": amount}, headers=headers)


def balance(client, driver_id="d1") -> str:
    return client.get(f"/drivers/{driver_id}/balance").json()["data"]["balance"]


def history(client, driver_id="d1", **params) -> dict:
    return client.get(f"/drivers/{driver_id}/history", params=params).json()["data"]


def scalar(sql: str, **params):
    """Run one SQL statement (committed) and return the first column of the first row."""
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar()
