# Netzence Carbon Credits

A small service that records carbon credits earned by drivers for completed
electric-vehicle rides, and lets drivers redeem them.

Stack: Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy 2, Alembic, pytest.
Design decisions and trade-offs are in [DECISIONS.md](DECISIONS.md).

## Run it

```bash
docker compose up
```

This starts PostgreSQL, runs the migrations, and starts the API.

| What | URL |
|---|---|
| API | http://localhost:8000 |
| Interactive API docs (try every endpoint) | http://localhost:8000/docs |
| Database browser (Adminer: system PostgreSQL, server `db`, user/password/db `netzence`) | http://localhost:8080 |
| Container logs (Dozzle) | http://localhost:8888 |

Optional demo data (three drivers covering every case):

```bash
make seed
```

## Tests

```bash
make test
```

The suite runs against a real PostgreSQL database (`netzence_test`, created
automatically). It builds the schema from the migrations and covers duplicate
events (including concurrent duplicates), 20 simultaneous redemptions against a
limited balance, FIFO spending, expiry, cancellations (including a cancellation
racing a redemption and one arriving before its ride), owed-credit recovery, a
simulated crash mid-redemption, and the database-level guards.

## Endpoints

| Method | Path | Called by |
|---|---|---|
| POST | `/rides/completed` | ride service |
| POST | `/rides/cancelled` | ride service |
| GET | `/rides/cancellations/pending` | operations / monitoring |
| GET | `/drivers/{id}/balance` | driver app |
| GET | `/drivers/{id}/history` | driver app |
| POST | `/drivers/{id}/redeem` | driver app |

Every response uses the same envelope: `{"message": "...", "data": {...}}`.
Errors return `{"message": "..."}` (plus `errors` for validation failures).

```bash
# a completed ride (idempotent on ride_id)
curl -X POST localhost:8000/rides/completed -H 'content-type: application/json' \
  -d '{"ride_id":"r1","driver_id":"d1","distance_km":12.5,"vehicle_type":"electric","completed_at":"2026-10-01T09:30:00Z"}'

curl localhost:8000/drivers/d1/balance
curl "localhost:8000/drivers/d1/history?page=1&per_page=20"

# redeem; the Idempotency-Key header is optional
curl -X POST localhost:8000/drivers/d1/redeem -H 'content-type: application/json' \
  -H 'Idempotency-Key: 7f3a9c1e-2b4d-4e8f-9a1b-3c5d7e9f1a2b' -d '{"amount":"1.000","reason":"Charging voucher"}'

# the ride was refunded after completion
curl -X POST localhost:8000/rides/cancelled -H 'content-type: application/json' \
  -d '{"ride_id":"r1","reason":"Refunded to passenger"}'
```

## How credits work

- **Formula:** 1 credit = 1 kg of CO2 avoided. An electric ride earns
  `distance_km x 0.12` credits (an EV avoids roughly 0.12 kg CO2/km compared
  with a petrol car). Hybrid, petrol and diesel rides are recorded with 0 credits.
- **Units:** amounts are stored as integer milli-credits (1 milli-credit = 1 g
  CO2), rounded down. The API returns them as strings such as `"1.500"`, never
  as floats.
- **Expiry:** credits expire 12 calendar months after the ride's `completed_at`.
  The balance only counts unexpired credits; redemptions spend the credits that
  expire soonest first.
- **Cancellations:** the ride's unspent credits are reversed. Credits it had
  already used are taken from the driver's other credits; anything they can't
  cover is recorded as owed and taken from the next credits they earn. The
  balance never goes negative, and the original credit entry always stays in
  the history.

## Integrating with the API

**Ride service.** Send `POST /rides/completed` when a ride finishes and
`POST /rides/cancelled` when a completed ride is refunded or cancelled. Both
are idempotent on `ride_id`, so retrying is always safe. Order doesn't matter: a
cancellation that arrives before its completion is kept (202) and applied when
the completion arrives.

**Driver app: `Idempotency-Key` on redeem.**
1. Generate a new UUID when the driver taps *Redeem*.
2. Keep it until you get a final answer (any 2xx or 4xx).
3. If the request times out or the connection drops, retry with the **same key
   and the same body**. The redemption happens at most once; a replay returns
   `200` with the original result.
4. The next tap gets a new key.

Reusing a key with a different body returns `409`. Without a key, every request
is a new redemption. Concurrent redemptions are safe either way: the driver's
row is locked, so the balance can never go below zero.

## Project layout

```
app/
  enums/, models/, exceptions/       one class per file
  http/controllers/                  thin endpoint functions
  http/requests/, http/resources/    input validation and response shapes
  services/core/                     business logic (rides, redemptions, balance/history)
  services/calculation/credits.py    credit formula and units
  traits/responses.py                response envelope
routes/api.py                        every route in one place
database/migrations/                 Alembic migrations
scripts/                             seed data, openapi.yml export
tests/
```

## Useful commands

| Command | Does |
|---|---|
| `make up` / `make down` | start / stop |
| `make fresh` | wipe the database and start again |
| `make seed` | reset the dev database with demo data |
| `make test` | run the test suite |
| `make migration name=add_x` | create a new migration |
| `make openapi` | regenerate `openapi.yml` from the code (a test checks it is current) |
