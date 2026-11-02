"""create redemption_allocations table

Revision ID: 2026_11_02_000004
Revises: 2026_11_02_000003
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000004"
down_revision = "2026_11_02_000003"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("redemption_allocations")
