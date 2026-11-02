"""create ledger_entries table

Revision ID: 2026_11_02_000003
Revises: 2026_11_02_000002
Create Date: 2026-11-02

Append-only: a trigger blocks UPDATE and DELETE.
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000003"
down_revision = "2026_11_02_000002"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("driver_id", sa.String(64), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("ride_id", sa.String(64), sa.ForeignKey("rides.ride_id")),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("entry_type IN ('credit','debit','reversal')", name="ck_ledger_entry_type"),
        sa.CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        sa.UniqueConstraint("driver_id", "idempotency_key", name="uq_ledger_driver_idempotency_key"),
    )
    op.create_index("ix_ledger_driver_created", "ledger_entries", ["driver_id", "created_at", "id"])
    op.create_index("ix_ledger_ride", "ledger_entries", ["ride_id"])

    op.execute(
        """
        CREATE FUNCTION ledger_entries_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entries is append-only (% not allowed)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_ledger_entries_append_only
            BEFORE UPDATE OR DELETE ON ledger_entries
            FOR EACH ROW EXECUTE FUNCTION ledger_entries_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_append_only ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS ledger_entries_append_only()")
    op.drop_table("ledger_entries")
