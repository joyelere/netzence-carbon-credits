"""add debt entry type

Revision ID: 2026_11_02_000008
Revises: 2026_11_02_000007
Create Date: 2026-11-02

A debt entry records credits added to drivers.credits_owed, so the history
shows where an owed amount came from.
"""

from alembic import op

revision = "2026_11_02_000008"
down_revision = "2026_11_02_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_ledger_entry_type", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_entry_type",
        "ledger_entries",
        "entry_type IN ('credit','debit','reversal','recovery','debt')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ledger_entry_type", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_entry_type", "ledger_entries", "entry_type IN ('credit','debit','reversal','recovery')"
    )
