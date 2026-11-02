"""cancelled rides keep no spendable credits

Revision ID: 2026_11_02_000009
Revises: 2026_11_02_000008
Create Date: 2026-11-02
"""

from alembic import op

revision = "2026_11_02_000009"
down_revision = "2026_11_02_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_rides_cancelled_has_no_credits", "rides", "status <> 'cancelled' OR credits_remaining = 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_rides_cancelled_has_no_credits", "rides", type_="check")
