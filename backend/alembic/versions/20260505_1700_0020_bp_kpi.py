"""business_plan + kpi: dashboards for executive reporting

Revision ID: 0020_bp_kpi
Revises: 0019_credit_delete_perm
Create Date: 2026-05-05 17:00:00.000000

Migrates the "Бизнес-план" and "KPI" modules from the legacy index.html
(lines 35357–42700, ~7300 lines).

Schema design:

  bp_records  — one row per (company, year, period, metric) tuple
                with plan/expect/fact triple.
                Period is one of: 'annual' | 'q1' | 'q2' | 'q3' | 'q4'.
                Metric is one of 22 BP_FIELDS keys (revenue, cogs, ...).

  bp_comments — free-text comment per (company, year, period).

  kpi_managers   — manager records per (company, year). Holds a position
                   (sort_order) within the company's manager list.

  kpi_indicators — leaf indicators per manager. Has annual plan/fact and
                   four quarter columns each with weight/plan/fact.

  kpi_comments   — free-text comment per (company, year, period).

Permissions added:
  bp.view, bp.edit, bp.import, bp.delete
  kpi.view, kpi.edit, kpi.import, kpi.delete
And bound to roles: ceo (all), debt (view-only), readonly (view-only).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from typing import Sequence, Union


revision: str = "0020_bp_kpi"
down_revision: Union[str, None] = "0019_credit_delete_perm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All 22 BP fields (mirror BP_FIELDS in legacy ~line 35398)
BP_METRICS = [
    "revenue", "cogs", "grossProfit",
    "opExpenses", "sellExp", "adminExp", "otherOpExp", "otherOpInc", "opProfit",
    "finIncome", "divIncome", "intIncome", "fxIncome", "otherFinInc",
    "finCost", "intExp", "fxLoss", "otherFinExp",
    "hhProfit", "pbt", "tax", "profit",
]

BP_PERIODS = ["annual", "q1", "q2", "q3", "q4"]


def upgrade() -> None:
    # ─── Business Plan ──────────────────────────────────────────────

    # bp_records: one row per (company, year, period, metric)
    op.create_table(
        "bp_records",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("plan", sa.Numeric(20, 3), nullable=True),
        sa.Column("expect", sa.Numeric(20, 3), nullable=True),
        sa.Column("fact", sa.Numeric(20, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "year", "period", "metric", name="uq_bp_records_co_year_period_metric"),
        sa.CheckConstraint(
            "period IN ('annual','q1','q2','q3','q4')",
            name="ck_bp_records_period",
        ),
    )
    op.create_index("ix_bp_records_co_year", "bp_records", ["company_id", "year"])
    op.create_index("ix_bp_records_year_period", "bp_records", ["year", "period"])

    # bp_comments: free-text comment per scope
    op.create_table(
        "bp_comments",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "year", "period", name="uq_bp_comments_co_year_period"),
    )

    # ─── KPI ────────────────────────────────────────────────────────

    # kpi_managers: top-level manager per (company, year)
    op.create_table(
        "kpi_managers",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("title", sa.Text, nullable=False),                     # full title
        sa.Column("short_title", sa.Text, nullable=True),                # short label used in cards
        sa.Column("role", sa.Text, nullable=True),                       # role description
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_kpi_managers_co_year", "kpi_managers", ["company_id", "year"])

    # kpi_indicators: leaf indicators
    op.create_table(
        "kpi_indicators",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("kpi_managers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("unit", sa.String(64), nullable=True),
        # Year-level
        sa.Column("weight", sa.Numeric(8, 3), nullable=False, server_default="0"),     # year weight
        sa.Column("plan_year", sa.Numeric(20, 3), nullable=True),
        sa.Column("fact_year", sa.Numeric(20, 3), nullable=True),
        # Quarter weights
        sa.Column("q1_weight", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("q2_weight", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("q3_weight", sa.Numeric(8, 3), nullable=False, server_default="0"),
        sa.Column("q4_weight", sa.Numeric(8, 3), nullable=False, server_default="0"),
        # Quarter plan/fact
        sa.Column("q1_plan", sa.Numeric(20, 3), nullable=True),
        sa.Column("q1_fact", sa.Numeric(20, 3), nullable=True),
        sa.Column("q2_plan", sa.Numeric(20, 3), nullable=True),
        sa.Column("q2_fact", sa.Numeric(20, 3), nullable=True),
        sa.Column("q3_plan", sa.Numeric(20, 3), nullable=True),
        sa.Column("q3_fact", sa.Numeric(20, 3), nullable=True),
        sa.Column("q4_plan", sa.Numeric(20, 3), nullable=True),
        sa.Column("q4_fact", sa.Numeric(20, 3), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_kpi_indicators_manager", "kpi_indicators", ["manager_id"])

    # kpi_comments
    op.create_table(
        "kpi_comments",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("period", sa.String(8), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("company_id", "year", "period", name="uq_kpi_comments_co_year_period"),
    )

    # ─── Permissions ────────────────────────────────────────────────
    perm_codes = [
        ("bp.view", "BP — просмотр"),
        ("bp.edit", "BP — редактирование"),
        ("bp.import", "BP — импорт"),
        ("bp.delete", "BP — удаление"),
        ("kpi.view", "KPI — просмотр"),
        ("kpi.edit", "KPI — редактирование"),
        ("kpi.import", "KPI — импорт"),
        ("kpi.delete", "KPI — удаление"),
    ]
    op.execute(
        "INSERT INTO permissions (id, code, name, module, description) VALUES " +
        ", ".join(
            f"(gen_random_uuid(), '{c}', '{n}', '{c.split('.')[0]}', '{n}')"
            for c, n in perm_codes
        ) +
        " ON CONFLICT (code) DO NOTHING"
    )

    # Grant to roles
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code IN ('admin', 'ceo')
          AND p.code IN ('bp.view','bp.edit','bp.import','bp.delete',
                         'kpi.view','kpi.edit','kpi.import','kpi.delete')
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code IN ('debt','readonly','imv_admin')
          AND p.code IN ('bp.view','kpi.view')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM role_permission WHERE permission_id IN (SELECT id FROM permissions WHERE code LIKE 'bp.%' OR code LIKE 'kpi.%')")
    op.execute("DELETE FROM permissions WHERE code LIKE 'bp.%' OR code LIKE 'kpi.%'")

    op.drop_table("kpi_comments")
    op.drop_index("ix_kpi_indicators_manager", table_name="kpi_indicators")
    op.drop_table("kpi_indicators")
    op.drop_index("ix_kpi_managers_co_year", table_name="kpi_managers")
    op.drop_table("kpi_managers")

    op.drop_table("bp_comments")
    op.drop_index("ix_bp_records_year_period", table_name="bp_records")
    op.drop_index("ix_bp_records_co_year", table_name="bp_records")
    op.drop_table("bp_records")
