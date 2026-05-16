"""financial models — Финансовая модель module

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-05 11:00:00

Tables created:

* `financial_models`           — header per (company × scenario)
* `financial_model_metrics`    — long-format (model_id, metric_code, year, value)
                                 covers P&L, Balance Sheet, Cash Flow, KPI cards,
                                 ratios, WACC components, sensitivity rows
* `financial_model_drivers`    — sub-aggregations keyed by (driver_code, sub_code, year)
                                 for things like airport loading per airport,
                                 CapEx by category (maintenance/growth),
                                 debt schedule (long-term/short-term)
* `financial_model_excel_blobs` — original Excel snapshots so user can re-parse
                                  without re-uploading

Design notes:

  • Long-format `metrics` (one row per cell) instead of wide JSONB → makes
    cell-level edits, audit history, and partial re-import trivial.
  • `unit` per metric so % values stay distinguishable from absolute UZSm.
  • `is_forecast` flag separates fact (2022-2024) from forecast (2025+).
  • `parent_code` allows hierarchy (e.g. "operating_profit" → "ebitda").

ID types:
  • Companies and users use UUID (see UUIDMixin).
  • Financial-model PKs are also UUID for consistency.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from typing import Sequence, Union


revision: str = "0017_financial_models"
down_revision: Union[str, None] = "0016_financials_detailed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Old placeholder table (created in migration 0001 with JSONB payload)
    # is being replaced by the new long-format schema below. Safe to drop —
    # the placeholder was never populated in production.
    op.execute("DROP TABLE IF EXISTS financial_models CASCADE")

    # ─── financial_models (header) ────────────────────────────────────────
    op.create_table(
        "financial_models",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("scenario", sa.String(64), nullable=False, server_default="base"),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="draft"
        ),  # draft / approved / archived
        sa.Column("period_start", sa.Integer, nullable=False),  # e.g. 2022
        sa.Column("period_end", sa.Integer, nullable=False),  # e.g. 2030
        sa.Column("forecast_start", sa.Integer, nullable=True),  # first forecast year
        sa.Column("currency", sa.String(8), nullable=False, server_default="UZS"),
        sa.Column(
            "unit_scale", sa.String(16), nullable=False, server_default="million"
        ),  # original / thousand / million / billion
        # WACC + CAPM inputs (editable in dashboard, persisted here)
        sa.Column("wacc", sa.Numeric(8, 4), nullable=True),
        sa.Column("risk_free_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("beta", sa.Numeric(8, 4), nullable=True),
        sa.Column("market_premium", sa.Numeric(8, 4), nullable=True),
        sa.Column("country_premium", sa.Numeric(8, 4), nullable=True),
        sa.Column("cost_debt_pretax", sa.Numeric(8, 4), nullable=True),
        sa.Column("tax_rate", sa.Numeric(8, 4), nullable=True),
        sa.Column("equity_weight", sa.Numeric(8, 4), nullable=True),
        sa.Column("debt_weight", sa.Numeric(8, 4), nullable=True),
        sa.Column("terminal_growth", sa.Numeric(8, 4), nullable=True),
        # Free-form notes / assumptions text
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "extra", JSONB, nullable=True
        ),  # parser leftovers / future-proofing
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.Column(
            "created_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("company_id", "scenario", name="uq_finmodel_co_scenario"),
    )

    # ─── financial_model_metrics (long-format cells) ──────────────────────
    op.create_table(
        "financial_model_metrics",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "model_id",
            UUID(as_uuid=True),
            sa.ForeignKey("financial_models.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "metric_code", sa.String(64), nullable=False
        ),  # e.g. 'revenue', 'ebitda', 'wc_dso'
        sa.Column("metric_name_ru", sa.String(256), nullable=False),
        sa.Column(
            "section", sa.String(32), nullable=False
        ),  # 'pnl' / 'bs' / 'cf' / 'kpi' / 'ratio' / 'wacc' / 'wc'
        sa.Column("parent_code", sa.String(64), nullable=True),
        sa.Column("indent_level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("year", sa.Integer, nullable=False),  # 2022..2030
        sa.Column("value", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "unit", sa.String(16), nullable=False, server_default="UZSm"
        ),  # UZSm / UZSb / pct / x / days / pp
        sa.Column("is_forecast", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "is_calculated", sa.Boolean, nullable=False, server_default="false"
        ),  # derived vs entered
        sa.Column(
            "source_link", sa.String(64), nullable=True
        ),  # Excel "Link" col: 'Revenue' / 'Cost' / 'Tax calculation' / etc.
        sa.UniqueConstraint(
            "model_id", "metric_code", "year", name="uq_finmodel_metric_cell"
        ),
    )
    op.create_index(
        "ix_finmodel_metrics_model_section",
        "financial_model_metrics",
        ["model_id", "section"],
    )

    # ─── financial_model_drivers (sub-aggregations) ───────────────────────
    op.create_table(
        "financial_model_drivers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "model_id",
            UUID(as_uuid=True),
            sa.ForeignKey("financial_models.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "driver_code", sa.String(64), nullable=False
        ),  # 'airport_loading' / 'capex_program' / 'debt_schedule'
        sa.Column(
            "sub_code", sa.String(64), nullable=False
        ),  # 'TAS' / 'maintenance' / 'long_term'
        sa.Column("sub_name_ru", sa.String(256), nullable=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=True),
        sa.Column(
            "unit", sa.String(16), nullable=False, server_default="UZSm"
        ),  # UZSm / pct / units
        sa.UniqueConstraint(
            "model_id",
            "driver_code",
            "sub_code",
            "year",
            name="uq_finmodel_driver_cell",
        ),
    )
    op.create_index(
        "ix_finmodel_drivers_model_driver",
        "financial_model_drivers",
        ["model_id", "driver_code"],
    )

    # ─── financial_model_excel_blobs (original snapshot for re-parse) ─────
    op.create_table(
        "financial_model_excel_blobs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "model_id",
            UUID(as_uuid=True),
            sa.ForeignKey("financial_models.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("raw_bytes", sa.LargeBinary, nullable=False),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "uploaded_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("financial_model_excel_blobs")
    op.drop_index(
        "ix_finmodel_drivers_model_driver", table_name="financial_model_drivers"
    )
    op.drop_table("financial_model_drivers")
    op.drop_index(
        "ix_finmodel_metrics_model_section", table_name="financial_model_metrics"
    )
    op.drop_table("financial_model_metrics")
    op.drop_table("financial_models")
