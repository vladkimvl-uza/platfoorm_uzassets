"""Add `payments_baseline_debt` column to cp_loans.

When user records the FIRST payment against a loan, this column is set to
whatever `debt_currency` was at that moment. Subsequent recomputes derive
`debt_currency = payments_baseline_debt − Σ principal_paid`.

This preserves historical snapshot values for the 316 existing loans —
recompute is a no-op until the user actively starts tracking payments.

Revision ID: 9aR_cp_payments_baseline
Revises:     9aQ_cp_payments
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aR_cp_payments_baseline"
down_revision: Union[str, None] = "9aQ_cp_payments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cp_loans",
        sa.Column("payments_baseline_debt", sa.Numeric(20, 2), nullable=True),
    )
    op.add_column(
        "cp_loans",
        sa.Column("payments_started_at", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cp_loans", "payments_started_at")
    op.drop_column("cp_loans", "payments_baseline_debt")
