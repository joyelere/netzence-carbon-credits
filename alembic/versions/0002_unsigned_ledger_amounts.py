"""store ledger amounts unsigned; entry_type gives the direction

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02

Before: credit = +1500, debit = -1000 (sign had to match entry_type).
After:  every amount is positive; entry_type (credit/debit/reversal) says
        whether it adds or subtracts. Balances come from credit_lots, not from
        summing the ledger, so a signed column bought us nothing.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_ledger_sign_matches_type", "ledger_entries", type_="check")
    # The ledger is append-only; lift the guard only for this one-off data fix.
    op.execute("ALTER TABLE ledger_entries DISABLE TRIGGER trg_ledger_entries_append_only")
    op.execute("UPDATE ledger_entries SET amount = abs(amount)")
    op.execute("ALTER TABLE ledger_entries ENABLE TRIGGER trg_ledger_entries_append_only")
    op.create_check_constraint("ck_ledger_amount_positive", "ledger_entries", "amount > 0")


def downgrade() -> None:
    op.drop_constraint("ck_ledger_amount_positive", "ledger_entries", type_="check")
    op.execute("ALTER TABLE ledger_entries DISABLE TRIGGER trg_ledger_entries_append_only")
    op.execute("UPDATE ledger_entries SET amount = -amount WHERE entry_type IN ('debit','reversal')")
    op.execute("ALTER TABLE ledger_entries ENABLE TRIGGER trg_ledger_entries_append_only")
    op.create_check_constraint(
        "ck_ledger_sign_matches_type",
        "ledger_entries",
        "(entry_type = 'credit' AND amount > 0) OR "
        "(entry_type IN ('debit','reversal') AND amount < 0)",
    )
