"""create procurement_closures table

Endpoint `/api/procurement/aggregate` queries `ProcurementClosure` model.
This migration creates the underlying table so paCompute()-style aggregation
can be done at request time (KPIs / rating / categories drilldowns).

Schema is denormalized for read performance — one row per (company, contract):
  - identity: company_id, year
  - product axis: category_id (KTRU prefix), product_code (full KTRU)
  - prices: unit_price (paid), market_avg (median benchmark), deviation_pct
  - volume: volume (qty), total_amount (UZS)
  - quality: is_clean (passed clustering bounds), is_dirty (excluded from KPI)
  - context: supplier_name, supplier_inn, sector, extra JSONB

Indexes optimised for: filter by company+year, group by category, sort by deviation.

Revision ID: 0022_procurement_closures
Revises: 0021_extend_source
Create Date: 2026-05-06 08:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0022_procurement_closures"
down_revision = "0021_extend_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "procurement_closures",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=True, index=True),
        sa.Column("closure_date", sa.Date(), nullable=True),

        # KTRU classification
        sa.Column("category_id", sa.String(64), nullable=True, index=True),
        sa.Column("product_code", sa.String(64), nullable=True, index=True),
        sa.Column("product_name", sa.String(1024), nullable=True),

        # Prices
        sa.Column("unit_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("market_avg", sa.Numeric(20, 4), nullable=True),
        sa.Column("deviation_pct", sa.Numeric(10, 4), nullable=True),

        # Volume
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("volume", sa.Numeric(20, 4), nullable=True),
        sa.Column("total_amount", sa.Numeric(28, 2), nullable=True),
        sa.Column("saved_amount", sa.Numeric(28, 2), nullable=True),

        # Supplier
        sa.Column("supplier_name", sa.String(512), nullable=True),
        sa.Column("supplier_inn", sa.String(32), nullable=True, index=True),

        # Source meta
        sa.Column("contract_id", sa.String(64), nullable=True, index=True),
        sa.Column("lot_id", sa.String(64), nullable=True),
        sa.Column("platform", sa.String(64), nullable=True),
        sa.Column("purchase_type", sa.String(32), nullable=True),
        sa.Column("region", sa.String(128), nullable=True),
        sa.Column("sector", sa.String(64), nullable=True, index=True),

        # Quality flags — see /pa cluster algorithm in legacy
        sa.Column("is_clean", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_dirty", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("dirty_reason", sa.String(255), nullable=True),

        sa.Column("extra", JSONB, nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    # Composite indexes for common query patterns
    op.create_index("ix_proc_closures_co_year", "procurement_closures",
                    ["company_id", "year"])
    op.create_index("ix_proc_closures_cat_year", "procurement_closures",
                    ["category_id", "year"])
    op.create_index("ix_proc_closures_pcode_year", "procurement_closures",
                    ["product_code", "year"])


def downgrade() -> None:
    op.drop_index("ix_proc_closures_pcode_year", table_name="procurement_closures")
    op.drop_index("ix_proc_closures_cat_year", table_name="procurement_closures")
    op.drop_index("ix_proc_closures_co_year", table_name="procurement_closures")
    op.drop_table("procurement_closures")
