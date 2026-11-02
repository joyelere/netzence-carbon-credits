"""add request_hash to ledger_entries table

Revision ID: 2026_11_02_000006
Revises: 2026_11_02_000005
Create Date: 2026-11-02

SHA-256 of the redeem body, stored with its idempotency key.
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000006"
down_revision = "2026_11_02_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ledger_entries", sa.Column("request_hash", sa.String(64)))
    op.create_check_constraint(
        "ck_ledger_key_has_request_hash",
        "ledger_entries",
        "(idempotency_key IS NULL) = (request_hash IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ledger_key_has_request_hash", "ledger_entries", type_="check")
    op.drop_column("ledger_entries", "request_hash")
