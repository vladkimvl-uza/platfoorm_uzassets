"""Create cp_payments table for manual loan repayment entries.

Each row = one human-entered repayment event against a loan (principal, interest,
optional penalty + fx rate snapshot + note + audit). Loan's `debt_currency` /
`debt_usd` are recomputed by the service layer after every payment write.

Revision ID: 9aQ_cp_payments
Revises:     9aP_finmodel_perms_admin_export
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "9aQ_cp_payments"
down_revision: Union[str, None] = "9aP_finmodel_perms_admin_export"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cp_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("loan_id", UUID(as_uuid=True), sa.ForeignKey("cp_loans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paid_date", sa.Date(), nullable=False),
        sa.Column("principal_paid", sa.Numeric(20, 2), nullable=False),
        sa.Column("interest_paid",  sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("penalty_paid",   sa.Numeric(20, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("fx_rate_to_uzs", sa.Numeric(20, 6), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Date(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_cp_payments_loan_id", "cp_payments", ["loan_id"])
    op.create_index("ix_cp_payments_paid_date", "cp_payments", ["paid_date"])
    op.create_index("ix_cp_payments_deleted_at", "cp_payments", ["deleted_at"])
    op.create_index("ix_cp_payments_loan_date", "cp_payments", ["loan_id", "paid_date"])


def downgrade() -> None:
    op.drop_index("ix_cp_payments_loan_date", table_name="cp_payments")
    op.drop_index("ix_cp_payments_deleted_at", table_name="cp_payments")
    op.drop_index("ix_cp_payments_paid_date", table_name="cp_payments")
    op.drop_index("ix_cp_payments_loan_id", table_name="cp_payments")
    op.drop_table("cp_payments")
