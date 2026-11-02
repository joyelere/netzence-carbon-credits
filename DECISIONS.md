# Decisions

**Time spent:** about 3.5 hours.

## The three biggest trade-offs

1. **A row lock per driver, not SERIALIZABLE or optimistic retries.** Every credit write first runs `SELECT ... FOR UPDATE` on the driver row, then reads the balance, so simultaneous redemptions queue and can't overspend. Cost: one driver's writes are serialised, which is fine at one driver's rate. `CHECK (credits_remaining >= 0)` is the backstop; removing the lock makes the 20-simultaneous-redemptions test fail.
2. **Expiry is evaluated when reading, not by a scheduled job.** Credits count only while `expires_at > now()`: nothing has to run on time and expiry is exact. Cost: no "expired" ledger row; each history credit line shows how much of it expired.
3. **Spent credits of a refunded ride are recovered, never clawed back into a negative balance.** The ride's unspent credits are reversed; what it had already used is taken from the driver's other credits; anything left is owed (`debt` entry) and taken from their next credits (`recovery` entry). Cost: two extra entry types and an owed column.

## Data model

- `drivers` (`credits_owed`): the row that gets locked.
- `rides` (`ride_id` PK, `credits`, `credits_remaining`, `expires_at`, `status`): the PK makes duplicate events impossible; `0 <= credits_remaining <= credits`; a cancelled ride has 0 left; only `completed` rides are spent from.
- `ledger_entries`: `credit | debit | reversal | recovery | debt`, positive amounts, append-only (a trigger blocks `UPDATE`/`DELETE`, so the original entry survives a cancellation), `UNIQUE (driver_id, idempotency_key)` plus `request_hash`.
- `credit_allocations`: what each debit or recovery took from each ride, soonest-expiring first, which is oldest first since every credit lives 12 months.
- `ride_cancellations`: `pending | applied`, no FK to `rides` because a cancellation can arrive first.

**Rejected:** separate `credit_lots` and `redemptions` tables (my first version, 7 tables): each ride had exactly one lot and each redemption one debit, so they duplicated `rides` and the ledger; merging also removed a join from every balance query. Also a holding period before credits are redeemable: refunds can arrive after any hold, so recovery is needed anyway.

## The open questions

- **Cancellation before completion:** stored as `pending` (202) and applied in the completion's transaction. Rejecting it would rely on the ride service retrying; if it gave up, a refunded ride would keep its credits. Pending rows never affect a balance and are never deleted; ones older than 48 hours are logged and listed at `/rides/cancellations/pending`.
- **Rounding:** integer milli-credits (1 = 1 g CO2), rounded down, returned as strings; no floating point anywhere. Only electric rides earn, 0.12 credits/km (assumptions in the README).
- **Crash halfway:** each request is one transaction (a test fails it after credits were deducted: nothing is saved). Ride events are idempotent on `ride_id`. Redeem requires an `Idempotency-Key`, stored with a SHA-256 fingerprint of the body (same key, different body: 409). Only the client can tell a retry from a second redemption, so the key is mandatory rather than optional: every client is retry-safe, at the cost of one header.

## With two more days

- Authenticate the ride service (signed requests / API key): it is trusted for completions and refunds, but the caller should be verified.
- An outbox `redemption.created` event so a rewards service fulfils redemptions reliably (vouchers and payouts are out of scope).
- Expire idempotency keys; remember failed outcomes too.
- Load-test lock contention; alert on stuck pending cancellations and growing owed balances.

## One thing that didn't work

After merging the lots into `rides`, the cancel-versus-redeem race test failed: 3.000 credits ended up 2.000 redeemed **and** 3.000 reversed. The cancellation read the ride before waiting for the driver lock and acted on a stale copy. Re-reading after taking the lock fixed it. Lesson: read the state a decision depends on under the lock.
