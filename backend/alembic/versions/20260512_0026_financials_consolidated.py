"""financial_reports: add is_consolidated flag + extend unique constraint

Revision ID: 0026_financials_consolidated
Revises: 0025_yearly_rates_uz_budget
Create Date: 2026-05-12 12:00:00.000000

IFRS-editor requirement (Pack 7.59):
- IFRS reports come in TWO scopes: consolidated (group) and standalone (parent).
- Same (company, year, quarter, standard, report_type) tuple can have BOTH
  scopes — they're different data.
- We add `is_consolidated` BOOL column (default TRUE for backward compat:
  ALL existing legacy store-migrated reports were consolidated/group-level).
- Existing unique constraint is replaced to include is_consolidated.

NSBU reports: always consolidated for our purposes — never standalone.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_financials_consolidated"
down_revision: Union[str, None] = "0025_yearly_rates_uz_budget"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the column with default=TRUE for all existing rows
    op.add_column(
        "financial_reports",
        sa.Column(
            "is_consolidated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            doc="True for consolidated/group-level IFRS reports (default); "
                "False for standalone/parent-only reports.",
        ),
    )

    # 2. Drop the old unique constraint
    op.drop_constraint("uq_fin_report_co_year_qtr_std_type", "financial_reports", type_="unique")

    # 3. Create the new unique constraint including is_consolidated
    op.create_unique_constraint(
        "uq_fin_report_co_year_qtr_std_type_scope",
        "financial_reports",
        ["company_id", "year", "quarter", "standard", "report_type", "is_consolidated"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_fin_report_co_year_qtr_std_type_scope", "financial_reports", type_="unique")
    op.create_unique_constraint(
        "uq_fin_report_co_year_qtr_std_type",
        "financial_reports",
        ["company_id", "year", "quarter", "standard", "report_type"],
    )
    op.drop_column("financial_reports", "is_consolidated")
