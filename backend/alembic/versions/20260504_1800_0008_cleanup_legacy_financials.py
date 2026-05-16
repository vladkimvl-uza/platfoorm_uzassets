"""cleanup old PNL/legacy financial reports

Revision ID: 0008_cleanup_legacy_financials
Revises: 0007_agency_ratings
Create Date: 2026-05-04 18:00:00.000000

The Part-3 FinancialsMigrator created reports with `report_type='PNL'` and
only 2 line codes ('REVENUE'/'NET_PROFIT' in CAPS). Those are incompatible
with the new editor catalog (which uses 'PL' and lowercase line codes).

This migration deletes the legacy data so the rewritten FinancialsMigrator
can repopulate cleanly. It only deletes rows that match the old shape.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0008_cleanup_legacy_financials"
down_revision: Union[str, None] = "0007_agency_ratings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete legacy lines (uppercase codes — REVENUE/NET_PROFIT)
    op.execute("""
        DELETE FROM financial_lines
        WHERE line_code IN ('REVENUE', 'NET_PROFIT')
    """)
    # Delete legacy reports (report_type='PNL' instead of 'PL')
    op.execute("""
        DELETE FROM financial_reports
        WHERE report_type = 'PNL'
    """)


def downgrade() -> None:
    # No-op: this is a one-way data cleanup.
    pass
