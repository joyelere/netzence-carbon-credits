"""rename credit_allocations constraints to match the table name

Revision ID: 2026_11_02_000010
Revises: 2026_11_02_000009
Create Date: 2026-11-02
"""

from alembic import op

revision = "2026_11_02_000010"
down_revision = "2026_11_02_000009"
branch_labels = None
depends_on = None

RENAMES = [
    ("redemption_allocations_pkey", "credit_allocations_pkey"),
    ("redemption_allocations_ledger_entry_id_fkey", "credit_allocations_ledger_entry_id_fkey"),
    ("redemption_allocations_ride_id_fkey", "credit_allocations_ride_id_fkey"),
]


def upgrade() -> None:
    for old, new in RENAMES:
        op.execute(f"ALTER TABLE credit_allocations RENAME CONSTRAINT {old} TO {new}")
    op.execute("ALTER SEQUENCE redemption_allocations_id_seq RENAME TO credit_allocations_id_seq")


def downgrade() -> None:
    op.execute("ALTER SEQUENCE credit_allocations_id_seq RENAME TO redemption_allocations_id_seq")
    for old, new in RENAMES:
        op.execute(f"ALTER TABLE credit_allocations RENAME CONSTRAINT {new} TO {old}")
