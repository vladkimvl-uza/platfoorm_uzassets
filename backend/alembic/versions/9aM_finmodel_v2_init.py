"""FinModel v2 init — 7 tables per finmodel-v2-handoff Phase 1.1.

Replaces v1 single-row JSONB blob. Each (company, year, row_code) is one
row in finmodel_cell_values; template defined in finmodel_template_rows;
macro split into global + per-company override; year-lock for approval;
scenarios for snapshot/restore; cell-level audit log (90d retention).

Revision ID: 9aM_finmodel_v2_init
Revises:     9aL_drop_finmodel_v1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9aM_finmodel_v2_init"
down_revision: Union[str, None] = "9aL_drop_finmodel_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Template lookup — 78 BS + 27 PL rows, static (seeded)
    op.create_table(
        "finmodel_template_rows",
        sa.Column("code", sa.String(16), primary_key=True),
        sa.Column("section", sa.String(8), nullable=False),  # BS | PL
        sa.Column("order_idx", sa.Integer, nullable=False),
        sa.Column("parent_code", sa.String(16), nullable=True),
        sa.Column("row_type", sa.String(16), nullable=False),  # input | subtotal | grand | check
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column("name_uz", sa.String(255), nullable=True),
        sa.Column("name_uz_cyr", sa.String(255), nullable=True),
        sa.Column("name_en", sa.String(255), nullable=True),
        sa.Column("formula", sa.Text, nullable=True),
        sa.Column("ifrs_category", sa.String(64), nullable=True),
        sa.Column("sign_convention", sa.String(8), nullable=True),  # positive | negative
        sa.Column("is_indent", sa.Integer, server_default="0"),
        sa.Column("legacy_note", sa.String(64), nullable=True),
    )
    op.create_index("ix_finmodel_template_section_order", "finmodel_template_rows", ["section", "order_idx"])

    # 2. Cell values — main data, one row per (co, year, code)
    op.create_table(
        "finmodel_cell_values",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("row_code", sa.String(16), sa.ForeignKey("finmodel_template_rows.code", ondelete="RESTRICT"), nullable=False),
        sa.Column("value", sa.Numeric(20, 2), nullable=True),
        sa.Column("is_calculated", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("company_id", "year", "row_code", name="uq_finmodel_cell"),
    )
    op.create_index("ix_finmodel_cell_co_year", "finmodel_cell_values", ["company_id", "year"])
    op.create_index("ix_finmodel_cell_code", "finmodel_cell_values", ["row_code"])

    # 3. Macro global — single source of truth fallback
    op.create_table(
        "finmodel_macro_global",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("year", sa.Integer, nullable=False, unique=True),
        sa.Column("uz_inflation", sa.Numeric(6, 4), nullable=True),
        sa.Column("us_inflation", sa.Numeric(6, 4), nullable=True),
        sa.Column("uzs_usd_avg_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("uzs_eur_avg_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("uzs_rub_avg_rate", sa.Numeric(12, 4), nullable=True),
        sa.Column("uzs_cny_avg_rate", sa.Numeric(12, 4), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # 4. Macro company override (optional)
    op.create_table(
        "finmodel_macro_company",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("uz_inflation", sa.Numeric(6, 4), nullable=True),
        sa.Column("us_inflation", sa.Numeric(6, 4), nullable=True),
        sa.Column("uzs_usd_avg_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("forecast_method", sa.String(32), server_default="uz_inflation"),
        sa.Column("manual_growth_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("dividend_payout_ratio", sa.Numeric(4, 3), server_default="0.500"),
        sa.Column("updated_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("company_id", "year", name="uq_finmodel_macro_co"),
    )

    # 5. Year lock (draft / review / approved / locked)
    op.create_table(
        "finmodel_year_lock",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approval_note", sa.Text, nullable=True),
        sa.UniqueConstraint("company_id", "year", name="uq_finmodel_year_lock"),
    )

    # 6. Scenarios — named snapshot of cells+macro
    op.create_table(
        "finmodel_scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_finmodel_scenarios_co", "finmodel_scenarios", ["company_id"])

    # 7. Cell comments
    op.create_table(
        "finmodel_cell_comments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("row_code", sa.String(16), nullable=False),
        sa.Column("comment_text", sa.Text, nullable=False),
        sa.Column("source_ref", sa.String(255), nullable=True),
        sa.Column("author_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_finmodel_comments_lookup", "finmodel_cell_comments", ["company_id", "year", "row_code"])

    # 8. Cell-level audit (high-volume, separate from RBAC audit)
    op.create_table(
        "finmodel_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("row_code", sa.String(16), nullable=False),
        sa.Column("value_before", sa.Numeric(20, 2), nullable=True),
        sa.Column("value_after", sa.Numeric(20, 2), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),  # manual | import | forecast | api | scenario_load
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_finmodel_audit_lookup", "finmodel_audit_log", ["company_id", "year", "row_code", "ts"])
    op.create_index("ix_finmodel_audit_ts", "finmodel_audit_log", ["ts"])


def downgrade() -> None:
    for tbl in [
        "finmodel_audit_log",
        "finmodel_cell_comments",
        "finmodel_scenarios",
        "finmodel_year_lock",
        "finmodel_macro_company",
        "finmodel_macro_global",
        "finmodel_cell_values",
        "finmodel_template_rows",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
