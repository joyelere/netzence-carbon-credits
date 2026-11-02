"""Cancelled rides whose credits were already used: taken from the driver's other
credits, and whatever can't be covered is owed and taken from the next credits."""

import pytest

from tests.conftest import balance, cancel, complete, days_ago, history, redeem, scalar


def owed(client, driver_id="d1") -> str:
    return client.get(f"/drivers/{driver_id}/balance").json()["data"]["owed"]


def test_used_credits_are_taken_from_other_credits_first(client):
    complete(client, "r1", km=25, completed_at=days_ago(20))  # 3.000, expires first
    complete(client, "r2", km=50, completed_at=days_ago(10))  # 6.000
    redeem(client, "2.000")                                    # taken from r1

    data = cancel(client, "r1").json()["data"]

    assert (data["reversed"], data["recovered"], data["owed"]) == ("1.000", "2.000", "0.000")
    assert balance(client) == "4.000"
    assert owed(client) == "0.000"


def test_what_cannot_be_covered_is_owed(client):
    complete(client, "r1", km=25, completed_at=days_ago(20))   # 3.000
    redeem(client, "2.500")                                     # 0.500 left on r1
    complete(client, "r2", km=5, completed_at=days_ago(10))    # 0.600

    data = cancel(client, "r1").json()["data"]

    assert (data["reversed"], data["recovered"], data["owed"]) == ("0.500", "0.600", "1.900")
    assert balance(client) == "0.000"
    assert owed(client) == "1.900"


def test_owed_credits_are_taken_from_the_next_ride(client):
    complete(client, "r1", km=25, completed_at=days_ago(20))  # 3.000
    redeem(client, "2.000")
    cancel(client, "r1")                                       # owes 2.000
    assert owed(client) == "2.000"

    complete(client, "r2", km=25, completed_at=days_ago(1))   # 3.000

    assert balance(client) == "1.000"
    assert owed(client) == "0.000"
    entries = history(client)["entries"]
    recovery = [e for e in entries if e["type"] == "recovery"]
    assert [e["amount"] for e in recovery] == ["2.000"]
    r2 = next(e for e in entries if e["type"] == "credit" and e["ride_id"] == "r2")
    assert (r2["recovered"], r2["remaining"], r2["status"]) == ("2.000", "1.000", "partially_used")


def test_a_debt_bigger_than_one_ride_is_paid_over_several_rides(client):
    complete(client, "r1", km=50, completed_at=days_ago(20))  # 6.000
    redeem(client, "6.000")
    cancel(client, "r1")                                       # owes 6.000

    complete(client, "r2", km=25, completed_at=days_ago(2))   # 3.000 -> all to the debt
    assert (balance(client), owed(client)) == ("0.000", "3.000")

    complete(client, "r3", km=50, completed_at=days_ago(1))   # 6.000 -> 3.000 debt, 3.000 balance
    assert (balance(client), owed(client)) == ("3.000", "0.000")


def test_cancelling_a_ride_that_repaid_a_debt_brings_the_debt_back(client):
    complete(client, "r1", km=25, completed_at=days_ago(20))  # 3.000
    redeem(client, "2.000")
    cancel(client, "r1")                                       # owes 2.000
    complete(client, "r2", km=25, completed_at=days_ago(1))   # 2.000 of it repays the debt

    data = cancel(client, "r2").json()["data"]

    assert (data["reversed"], data["recovered"], data["owed"]) == ("1.000", "0.000", "2.000")
    assert (balance(client), owed(client)) == ("0.000", "2.000")


def test_a_ride_with_an_early_cancellation_does_not_repay_debt(client):
    complete(client, "r1", km=25, completed_at=days_ago(20))
    redeem(client, "2.000")
    cancel(client, "r1")                                       # owes 2.000
    cancel(client, "r2")                                       # r2 not seen yet: pending

    complete(client, "r2", km=25, completed_at=days_ago(1))   # credited and reversed at once

    assert (balance(client), owed(client)) == ("0.000", "2.000")


def test_every_credit_line_and_the_owed_total_add_up(client):
    complete(client, "a", km=25, completed_at=days_ago(30))
    complete(client, "b", km=10, completed_at=days_ago(20))
    redeem(client, "3.500")
    cancel(client, "a")
    complete(client, "c", km=50, completed_at=days_ago(5))
    redeem(client, "1.000")
    cancel(client, "b")

    entries = history(client)["entries"]
    for e in (e for e in entries if e["type"] == "credit"):
        parts = sum(float(e[k]) for k in ("used", "recovered", "expired", "reversed", "remaining"))
        assert parts == pytest.approx(float(e["amount"])), e["ride_id"]

    owed_total = scalar("SELECT coalesce(sum(owed_amount), 0) FROM ride_cancellations")
    repaid_later = scalar(
        "SELECT coalesce(sum(amount), 0) FROM ledger_entries WHERE entry_type = 'recovery' AND ride_id IS NULL"
    )
    assert scalar("SELECT credits_owed FROM drivers") == owed_total - repaid_later
    assert float(balance(client)) >= 0
