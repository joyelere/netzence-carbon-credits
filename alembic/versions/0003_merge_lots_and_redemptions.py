"""simplify: 7 tables -> 5

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02

Two tables duplicated others:
- credit_lots: one ride always produced exactly one lot, so its columns
  (remaining, expires_at) now live on `rides` as credits_remaining / expires_at.
- redemptions: every redemption already wrote a 'debit' ledger entry, so that
  entry IS the redemption; idempotency_key moves onto ledger_entries.
lot_consumptions becomes redemption_allocations (debit entry -> ride).

Existing data is carried over. This migration is one-way: downgrade raises.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # ---- rides absorb credit_lots -------------------------------------------
    op.add_column("rides", sa.Column("credits_remaining", sa.BigInteger))
    op.add_column("rides", sa.Column("expires_at", TS))
    op.add_column("rides", sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()))
    op.execute(
        """
        UPDATE rides r SET credits_remaining = cl.remaining, expires_at = cl.expires_at
          FROM credit_lots cl WHERE cl.ride_id = r.ride_id;
        UPDATE rides SET credits_remaining = 0 WHERE credits_remaining IS NULL;
        UPDATE rides SET expires_at = completed_at + interval '12 months' WHERE expires_at IS NULL;
        """
    )
    op.alter_column("rides", "credits_remaining", nullable=False)
    op.alter_column("rides", "expires_at", nullable=False)
    op.create_check_constraint(
        "ck_rides_remaining_in_range", "rides", "credits_remaining >= 0 AND credits_remaining <= credits"
    )
    # FIFO redeem + balance both scan a driver's rides by expiry
    op.create_index("ix_rides_driver_expires", "rides", ["driver_id", "expires_at"])

    # ---- ledger_entries absorb redemptions ----------------------------------
    op.add_column("ledger_entries", sa.Column("idempotency_key", sa.String(128)))
    op.execute("ALTER TABLE ledger_entries DISABLE TRIGGER trg_ledger_entries_append_only")
    op.execute(
        """
        UPDATE ledger_entries le SET idempotency_key = r.idempotency_key
          FROM redemptions r WHERE le.redemption_id = r.id
        """
    )
    op.execute("ALTER TABLE ledger_entries ENABLE TRIGGER trg_ledger_entries_append_only")
    op.create_unique_constraint(
        "uq_ledger_driver_idempotency_key", "ledger_entries", ["driver_id", "idempotency_key"]
    )

    # ---- lot_consumptions -> redemption_allocations --------------------------
    op.create_table(
        "redemption_allocations",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("ledger_entry_id", sa.BigInteger, sa.ForeignKey("ledger_entries.id"), nullable=False),
        sa.Column("ride_id", sa.String(64), sa.ForeignKey("rides.ride_id"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_allocations_amount_positive"),
    )
    op.create_index("ix_allocations_ledger_entry", "redemption_allocations", ["ledger_entry_id"])
    op.create_index("ix_allocations_ride", "redemption_allocations", ["ride_id"])
    op.execute(
        """
        INSERT INTO redemption_allocations (ledger_entry_id, ride_id, amount, created_at)
        SELECT le.id, cl.ride_id, lc.amount, r.created_at
          FROM lot_consumptions lc
          JOIN redemptions r     ON r.id = lc.redemption_id
          JOIN ledger_entries le ON le.redemption_id = r.id AND le.entry_type = 'debit'
          JOIN credit_lots cl    ON cl.id = lc.lot_id
         ORDER BY lc.id
        """
    )

    # ---- drop what is now redundant -----------------------------------------
    op.drop_column("ledger_entries", "redemption_id")
    op.drop_column("ledger_entries", "lot_id")
    op.drop_table("lot_consumptions")
    op.drop_table("redemptions")
    op.drop_table("credit_lots")


def downgrade() -> None:
    raise NotImplementedError("0003 merges tables and is one-way; restore from a backup to go back.")
