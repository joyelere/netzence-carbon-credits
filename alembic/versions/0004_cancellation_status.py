"""ride_cancellations: explicit status (pending | applied) and applied_at

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-02

pending = the cancellation arrived but its ride has not (yet) been completed,
          so nothing has been reversed.
applied = the ride's unspent credits were reversed at applied_at.

A pending row never affects any balance. Pending rows are never deleted or
auto-closed: if the completion turns up late, it must still be reversed.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ride_cancellations",
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column("ride_cancellations", sa.Column("applied_at", sa.DateTime(timezone=True)))

    # Existing cancellations whose ride exists were applied when both were present.
    op.execute(
        """
        UPDATE ride_cancellations c
           SET status = 'applied', applied_at = greatest(c.received_at, r.created_at)
          FROM rides r
         WHERE r.ride_id = c.ride_id
        """
    )

    op.create_check_constraint(
        "ck_cancellations_status", "ride_cancellations", "status IN ('pending','applied')"
    )
    # status and applied_at can never disagree
    op.create_check_constraint(
        "ck_cancellations_applied_at_matches_status",
        "ride_cancellations",
        "(status = 'applied') = (applied_at IS NOT NULL)",
    )
    # fast lookup of stuck pending cancellations
    op.create_index(
        "ix_cancellations_pending_received",
        "ride_cancellations",
        ["received_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_cancellations_pending_received", table_name="ride_cancellations")
    op.drop_constraint("ck_cancellations_applied_at_matches_status", "ride_cancellations", type_="check")
    op.drop_constraint("ck_cancellations_status", "ride_cancellations", type_="check")
    op.drop_column("ride_cancellations", "applied_at")
    op.drop_column("ride_cancellations", "status")
