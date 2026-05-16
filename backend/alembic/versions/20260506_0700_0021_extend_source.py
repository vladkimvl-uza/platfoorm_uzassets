"""extend financial_reports.source to varchar(255)

The detailed Excel-import endpoint stores `excel-confirm:<original_filename>`
in `financial_reports.source` (e.g. "excel-confirm:High Level Financials v4 (2024).xlsx",
49 chars). The original VARCHAR(32) overflows → asyncpg raises
StringDataRightTruncationError → 500.

Revision ID: 0021_extend_source
Revises: 0020_bp_kpi
Create Date: 2026-05-06 07:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers
revision = "0021_extend_source"
down_revision = "0020_bp_kpi"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "financial_reports",
        "source",
        existing_type=sa.String(length=32),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Truncate any longer values to 32 chars before reverting (lossy).
    op.execute("UPDATE financial_reports SET source = LEFT(source, 32) WHERE LENGTH(source) > 32")
    op.alter_column(
        "financial_reports",
        "source",
        existing_type=sa.String(length=255),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
