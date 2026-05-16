"""financial_reports: add is_detailed flag + section grouping

Revision ID: 0016_financials_detailed
Revises: 0015_companies_name_sync
Create Date: 2026-05-04 23:30:00.000000

Detailed audited МСФО reports (Property/plant/equipment, Inventories,
Trade and other receivables, Share capital, Translation reserve, Retained
earnings, Borrowings LT/ST, Employee benefits, Environmental obligations,
Deferred tax liabilities, Trade and other payables, etc.) are imported from
audit Excel files and stored in the SAME financial_lines table — no new
table needed. We just need:

  1. financial_reports.is_detailed BOOL — to distinguish "summary" reports
     (the existing 26 codes from /pf/financials in Firebase) from detailed
     audit reports.
  2. financial_lines.section_label STRING — non-line group header rendered
     before that line in UI (e.g. "ASSETS", "EQUITY", "LIABILITIES",
     "NON-CURRENT LIABILITIES").
  3. financial_lines.indent_level INT — how deep the line is in the hierarchy
     (0 = top, 1 = sub, 2 = sub-sub). Used together with parent_code.

Backwards compatible: existing rows get is_detailed=false, indent_level=0,
section_label=NULL — UI keeps showing them in summary tab.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_financials_detailed"
down_revision: Union[str, None] = "0015_companies_name_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "financial_reports",
        sa.Column("is_detailed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "financial_lines",
        sa.Column("section_label", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "financial_lines",
        sa.Column("indent_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_financial_reports_is_detailed",
        "financial_reports",
        ["company_id", "is_detailed", "standard"],
    )


def downgrade() -> None:
    op.drop_index("ix_financial_reports_is_detailed", table_name="financial_reports")
    op.drop_column("financial_lines", "indent_level")
    op.drop_column("financial_lines", "section_label")
    op.drop_column("financial_reports", "is_detailed")
