"""create drivers table

Revision ID: 2026_11_02_000001
Revises: 
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000001"
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


def downgrade() -> None:
    op.drop_table("drivers")
