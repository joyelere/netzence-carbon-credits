"""create credit tables

Revision ID: 0001
Revises:
Create Date: 2026-11-02

Constraints here are the real safety net — even if application code has a bug,
Postgres refuses duplicate rides, negative lot balances and wrong-signed entries.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "drivers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "rides",
        # PK on ride_id = the same ride event can never be stored twice
        sa.Column("ride_id", sa.String(64), primary_key=True),
        sa.Column("driver_id", sa.String(64), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("distance_km", sa.Numeric(10, 3), nullable=False),
        sa.Column("vehicle_type", sa.String(16), nullable=False),
        sa.Column("completed_at", TS, nullable=False),
        sa.Column("credits", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cancelled_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("distance_km >= 0", name="ck_rides_distance_non_negative"),
        sa.CheckConstraint("credits >= 0", name="ck_rides_credits_non_negative"),
        sa.CheckConstraint(
            "vehicle_type IN ('electric','hybrid','petrol','diesel')", name="ck_rides_vehicle_type"
        ),
        sa.CheckConstraint("status IN ('completed','cancelled')", name="ck_rides_status"),
    )
    op.create_index("ix_rides_driver_id", "rides", ["driver_id"])

    op.create_table(
        "ride_cancellations",
        sa.Column("ride_id", sa.String(64), primary_key=True),
        sa.Column("reason", sa.Text),
        sa.Column("received_at", TS, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "credit_lots",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("driver_id", sa.String(64), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("ride_id", sa.String(64), sa.ForeignKey("rides.ride_id"), nullable=False, unique=True),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("remaining", sa.BigInteger, nullable=False),
        sa.Column("earned_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_lots_amount_positive"),
        # a lot can never be over-spent or go negative
        sa.CheckConstraint("remaining >= 0 AND remaining <= amount", name="ck_lots_remaining_in_range"),
        sa.CheckConstraint("expires_at > earned_at", name="ck_lots_expiry_after_earned"),
    )
    # FIFO redeem + balance both scan a driver's lots by expiry
    op.create_index("ix_credit_lots_driver_expires", "credit_lots", ["driver_id", "expires_at"])

    op.create_table(
        "redemptions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("driver_id", sa.String(64), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("idempotency_key", sa.String(128)),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount > 0", name="ck_redemptions_amount_positive"),
        sa.UniqueConstraint("driver_id", "idempotency_key", name="uq_redemptions_driver_idempotency_key"),
    )

    op.create_table(
        "lot_consumptions",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("redemption_id", sa.BigInteger, sa.ForeignKey("redemptions.id"), nullable=False),
        sa.Column("lot_id", sa.BigInteger, sa.ForeignKey("credit_lots.id"), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_consumptions_amount_positive"),
    )
    op.create_index("ix_lot_consumptions_redemption", "lot_consumptions", ["redemption_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("driver_id", sa.String(64), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("ride_id", sa.String(64), sa.ForeignKey("rides.ride_id")),
        sa.Column("redemption_id", sa.BigInteger, sa.ForeignKey("redemptions.id")),
        sa.Column("lot_id", sa.BigInteger, sa.ForeignKey("credit_lots.id")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        # sign must match the type: credits add, debits/reversals subtract
        sa.CheckConstraint(
            "(entry_type = 'credit' AND amount > 0) OR "
            "(entry_type IN ('debit','reversal') AND amount < 0)",
            name="ck_ledger_sign_matches_type",
        ),
    )
    op.create_index("ix_ledger_driver_created", "ledger_entries", ["driver_id", "created_at", "id"])

    # The ledger is append-only: block UPDATE/DELETE at the database level.
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
    for table in (
        "ledger_entries",
        "lot_consumptions",
        "redemptions",
        "credit_lots",
        "ride_cancellations",
        "rides",
        "drivers",
    ):
        op.drop_table(table)
