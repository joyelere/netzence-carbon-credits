"""create ride_cancellations table

Revision ID: 2026_11_02_000005
Revises: 2026_11_02_000004
Create Date: 2026-11-02

No FK to rides: a cancellation can arrive before its ride.
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000005"
down_revision = "2026_11_02_000004"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "ride_cancellations",
        sa.Column("ride_id", sa.String(64), primary_key=True),
        sa.Column("reason", sa.Text),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("received_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", TS),
        sa.CheckConstraint("status IN ('pending','applied')", name="ck_cancellations_status"),
        sa.CheckConstraint(
            "(status = 'applied') = (applied_at IS NOT NULL)", name="ck_cancellations_applied_at_matches_status"
        ),
    )
    op.create_index(
        "ix_cancellations_pending_received",
        "ride_cancellations",
        ["received_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("ride_cancellations")
