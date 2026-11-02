"""create rides table

Revision ID: 2026_11_02_000002
Revises: 2026_11_02_000001
Create Date: 2026-11-02

Amounts are milli-credits (1 credit = 1000).
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000002"
down_revision = "2026_11_02_000001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "rides",
        sa.Column("ride_id", sa.String(64), primary_key=True),
        sa.Column("driver_id", sa.String(64), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("distance_km", sa.Numeric(10, 3), nullable=False),
        sa.Column("vehicle_type", sa.String(16), nullable=False),
        sa.Column("completed_at", TS, nullable=False),
        sa.Column("credits", sa.BigInteger, nullable=False),
        sa.Column("credits_remaining", sa.BigInteger, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cancelled_at", TS),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("distance_km >= 0", name="ck_rides_distance_non_negative"),
        sa.CheckConstraint("credits >= 0", name="ck_rides_credits_non_negative"),
        sa.CheckConstraint(
            "credits_remaining >= 0 AND credits_remaining <= credits", name="ck_rides_remaining_in_range"
        ),
        sa.CheckConstraint("expires_at > completed_at", name="ck_rides_expiry_after_completion"),
        sa.CheckConstraint(
            "vehicle_type IN ('electric','hybrid','petrol','diesel')", name="ck_rides_vehicle_type"
        ),
        sa.CheckConstraint("status IN ('completed','cancelled')", name="ck_rides_status"),
    )
    op.create_index("ix_rides_driver_expires", "rides", ["driver_id", "expires_at"])


def downgrade() -> None:
    op.drop_table("rides")
