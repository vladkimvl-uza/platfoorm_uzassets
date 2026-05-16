"""Companies & Sectors advanced — colors, badges, year overrides, hierarchy (Pack 9.2).

Revision ID: 9a2_companies_advanced
Revises: 9a1_rbac_granular
Create Date: 20260512-2300

Adds:
  1. companies: primary_color, secondary_color, badges (jsonb), status,
                is_pinned, include_in_rollups, module_flags (jsonb),
                parent_id, portfolio_start_year, primary_currency,
                fy_start_month, track_inflation, bloomberg_ticker,
                isin, lei, tags (jsonb), aliases (jsonb)
  2. sectors:   color_secondary, icon_name, short_badge, aliases (jsonb)
  3. company_year_override table — per-year visibility / rename / sector override
  4. Seed company status enum reference values into seed data
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a2_companies_advanced"
down_revision = "9a1_rbac_granular"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. Extend companies ─────
    op.add_column("companies", sa.Column("primary_color",        sa.String(9),  nullable=True))
    op.add_column("companies", sa.Column("secondary_color",      sa.String(9),  nullable=True))
    op.add_column("companies", sa.Column("badges",               postgresql.JSONB, nullable=True))
    op.add_column("companies", sa.Column("status",               sa.String(32), nullable=True, server_default=sa.text("'active'")))
    op.add_column("companies", sa.Column("is_pinned",            sa.Boolean,    nullable=False, server_default=sa.text("false")))
    op.add_column("companies", sa.Column("include_in_rollups",   sa.Boolean,    nullable=False, server_default=sa.text("true")))
    op.add_column("companies", sa.Column("module_flags",         postgresql.JSONB, nullable=True))
    op.add_column("companies", sa.Column("parent_id",            postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("companies", sa.Column("portfolio_start_year", sa.Integer,    nullable=True))
    op.add_column("companies", sa.Column("primary_currency",     sa.String(3),  nullable=False, server_default=sa.text("'UZS'")))
    op.add_column("companies", sa.Column("fy_start_month",       sa.Integer,    nullable=False, server_default=sa.text("1")))
    op.add_column("companies", sa.Column("track_inflation",      sa.Boolean,    nullable=False, server_default=sa.text("true")))
    op.add_column("companies", sa.Column("bloomberg_ticker",     sa.String(32), nullable=True))
    op.add_column("companies", sa.Column("isin",                 sa.String(32), nullable=True))
    op.add_column("companies", sa.Column("lei",                  sa.String(32), nullable=True))
    op.add_column("companies", sa.Column("tags",                 postgresql.JSONB, nullable=True))
    op.add_column("companies", sa.Column("aliases",              postgresql.JSONB, nullable=True))

    op.create_foreign_key(
        "fk_companies_parent", "companies", "companies",
        ["parent_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_companies_parent_id", "companies", ["parent_id"])
    op.create_index("ix_companies_status",    "companies", ["status"])
    op.create_index("ix_companies_pinned",    "companies", ["is_pinned"],
                    postgresql_where=sa.text("is_pinned = true"))

    # ───── 2. Extend sectors ─────
    op.add_column("sectors", sa.Column("color_secondary", sa.String(9),  nullable=True))
    op.add_column("sectors", sa.Column("icon_name",       sa.String(64), nullable=True))
    op.add_column("sectors", sa.Column("short_badge",     sa.String(8),  nullable=True))
    op.add_column("sectors", sa.Column("aliases",         postgresql.JSONB, nullable=True))

    # ───── 3. company_year_override ─────
    op.create_table(
        "company_year_override",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("company_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year",        sa.Integer,    nullable=False),
        sa.Column("is_hidden",   sa.Boolean,    nullable=False, server_default=sa.text("false")),
        sa.Column("name_override",   sa.String(255), nullable=True),
        sa.Column("sector_override_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("exclusion_reason",   sa.String(64),  nullable=True),
        sa.Column("notes",         sa.String(512), nullable=True),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sector_override_id"], ["sectors.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("company_id", "year", name="uq_company_year_override"),
    )
    op.create_index("ix_cyo_company", "company_year_override", ["company_id"])
    op.create_index("ix_cyo_year",    "company_year_override", ["year"])

    # ───── 4. Seed defaults: copy color_hex from sectors → companies if not set ─────
    op.execute("""
        UPDATE companies c
        SET primary_color = s.color_hex
        FROM sectors s
        WHERE c.sector_id = s.id
          AND c.primary_color IS NULL
          AND s.color_hex IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_cyo_year",    table_name="company_year_override")
    op.drop_index("ix_cyo_company", table_name="company_year_override")
    op.drop_table("company_year_override")

    op.drop_column("sectors", "aliases")
    op.drop_column("sectors", "short_badge")
    op.drop_column("sectors", "icon_name")
    op.drop_column("sectors", "color_secondary")

    op.drop_index("ix_companies_pinned",    table_name="companies")
    op.drop_index("ix_companies_status",    table_name="companies")
    op.drop_index("ix_companies_parent_id", table_name="companies")
    op.drop_constraint("fk_companies_parent", "companies", type_="foreignkey")

    for col in [
        "aliases", "tags", "lei", "isin", "bloomberg_ticker",
        "track_inflation", "fy_start_month", "primary_currency",
        "portfolio_start_year", "parent_id", "module_flags",
        "include_in_rollups", "is_pinned", "status",
        "badges", "secondary_color", "primary_color",
    ]:
        op.drop_column("companies", col)
