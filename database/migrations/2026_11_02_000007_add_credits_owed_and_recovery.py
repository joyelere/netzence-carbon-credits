"""add credits owed and recovery entries

Revision ID: 2026_11_02_000007
Revises: 2026_11_02_000006
Create Date: 2026-11-02

When a cancelled ride's credits were already used, they are taken back from the
driver's other credits; whatever can't be covered is recorded in
drivers.credits_owed and taken from the next credits the driver earns.
"""

import sqlalchemy as sa
from alembic import op

revision = "2026_11_02_000007"
down_revision = "2026_11_02_000006"
branch_labels = None
depends_on = None

AMOUNTS = ("reversed_amount", "recovered_amount", "owed_amount")


def upgrade() -> None:
    op.add_column("drivers", sa.Column("credits_owed", sa.BigInteger, nullable=False, server_default="0"))
    op.create_check_constraint("ck_drivers_credits_owed_non_negative", "drivers", "credits_owed >= 0")

    op.drop_constraint("ck_ledger_entry_type", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_entry_type", "ledger_entries", "entry_type IN ('credit','debit','reversal','recovery')"
    )

    # now records what debit and recovery entries took from each ride
    op.rename_table("redemption_allocations", "credit_allocations")

    for column in AMOUNTS:
        op.add_column("ride_cancellations", sa.Column(column, sa.BigInteger))
    op.execute(
        """
        UPDATE ride_cancellations c
           SET reversed_amount = coalesce((SELECT sum(amount) FROM ledger_entries
                                            WHERE ride_id = c.ride_id AND entry_type = 'reversal'), 0),
               recovered_amount = 0,
               owed_amount = 0
         WHERE status = 'applied'
        """
    )
    op.create_check_constraint(
        "ck_cancellations_amounts_match_status",
        "ride_cancellations",
        "(status = 'pending' AND reversed_amount IS NULL AND recovered_amount IS NULL AND owed_amount IS NULL)"
        " OR (status = 'applied' AND reversed_amount >= 0 AND recovered_amount >= 0 AND owed_amount >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_cancellations_amounts_match_status", "ride_cancellations", type_="check")
    for column in AMOUNTS:
        op.drop_column("ride_cancellations", column)
    op.rename_table("credit_allocations", "redemption_allocations")
    op.drop_constraint("ck_ledger_entry_type", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_entry_type", "ledger_entries", "entry_type IN ('credit','debit','reversal')"
    )
    op.drop_constraint("ck_drivers_credits_owed_non_negative", "drivers", type_="check")
    op.drop_column("drivers", "credits_owed")
