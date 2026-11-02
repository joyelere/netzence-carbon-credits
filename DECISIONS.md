# Decisions

**Time spent:** _TODO_

## The three biggest trade-offs

1. **A row lock per driver, not SERIALIZABLE or optimistic retries.** Every write to a driver's credits first runs `SELECT ... FOR UPDATE` on the driver row, then reads the balance. Simultaneous redemptions for one driver queue instead of racing, so the balance can't go below zero, and there are no retry loops to get wrong. The cost is that one driver's writes are serialised, which is fine at one driver's request rate. A `CHECK (credits_remaining >= 0)` is the backstop.
2. **Expiry is evaluated when reading, not by a scheduled job.** A ride's credits count only while `expires_at > now()`. Nothing has to run on time and expiry is exact to the second. The cost is that there is no "expired" ledger row; each credit line in the history shows how much of it expired instead.
3. **A refunded ride's credits that were already spent are recovered, not clawed back into a negative balance.** The ride's unspent credits are reversed; what it had already used is taken from the driver's other credits; anything still uncovered is recorded as owed (`debt` entry) and taken from the next credits they earn (`recovery` entry). This keeps the balance at zero or above, at the cost of two extra entry types and an owed column.

## Data model

- `drivers` (`id`, `credits_owed`): the row that gets locked.
- `rides` (`ride_id` PK, `credits`, `credits_remaining`, `expires_at`, `status`): the primary key makes a duplicate event impossible to store; `CHECK 0 <= credits_remaining <= credits`, and a cancelled ride must have 0 left. Only `completed` rides are ever spent from.
- `ledger_entries`: the history: `credit | debit | reversal | recovery | debt`, amounts always positive. A trigger blocks `UPDATE`/`DELETE`, so the original entry always survives a cancellation. `UNIQUE (driver_id, idempotency_key)` plus a `request_hash`.
- `credit_allocations`: how much each debit or recovery took from each ride (the FIFO trail).
- `ride_cancellations`: `pending | applied`, with no FK to `rides`, because a cancellation can arrive first.

**Rejected:** my first version had separate `credit_lots` and `redemptions` tables (7 in all). Every ride produced exactly one lot and every redemption exactly one debit entry, so both duplicated other tables. I merged them, which also removed a join from every balance query. I also rejected a holding period before credits become redeemable: refunds can arrive after any hold, so recovery is needed anyway.

## The open questions

- **Cancellation before completion:** stored as `pending` (202) and applied in the same transaction as the completion when it arrives. Rejecting it with an error would rely on the ride service retrying; if it gave up, a refunded ride would keep its credits. Pending rows never affect a balance, are never auto-deleted, and ones older than 48 hours are listed at `/rides/cancellations/pending` and logged.
- **Rounding:** integers in milli-credits (1 = 1 g CO2), rounded down at 0.12 credits/km, returned as strings. No floating point anywhere.
- **Crash halfway:** each request is one transaction, so it is all or nothing (a test injects a failure after credits were deducted: nothing is saved). Ride events are idempotent on `ride_id`. Redeem retries are safe with an `Idempotency-Key`, stored with a SHA-256 fingerprint of the body; reusing a key with a different body returns 409. Without a key, the server can't tell a retry from a second redemption, so that guarantee needs the client.

## With two more days

- Authenticate the ride service's calls (signed requests / API key).
- Publish a `redemption.created` event through an outbox table so a rewards service can fulfil redemptions reliably.
- Expire idempotency keys and remember failed outcomes too.
- Load-test lock contention; alert on stuck pending cancellations and growing owed balances.

## One thing that didn't work

After merging the lots into `rides`, the test that races a cancellation against a redemption failed: 3.000 credits produced 2.000 redeemed **and** 3.000 reversed. The cancellation read the ride before waiting for the driver lock, then acted on a stale copy. Re-reading the ride after taking the lock fixed it. The lesson: any state a decision depends on must be read under the lock.
