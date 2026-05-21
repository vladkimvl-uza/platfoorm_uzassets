"""Company Library (MDM) — Phase 1 schema.

- Add `companies.custom_data` JSONB column for sector-scoped/custom field values
- field_definitions   — schema of available custom fields (system + user-created)
- company_library_views — per-user column presets (table layout, filters, sort)
- company_library_tabs  — system + custom tabs for the Detail view

Revision ID: 9aJ_company_library
Revises:     9aI_procurement_closures_seed
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9aJ_company_library"
down_revision: Union[str, None] = "9aI_procurement_closures_seed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Companies: custom_data JSONB ────────────────────────────────
    op.add_column(
        "companies",
        sa.Column(
            "custom_data",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ── 2. field_definitions ───────────────────────────────────────────
    op.create_table(
        "field_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column("name_uz", sa.String(255), nullable=True),
        sa.Column("name_en", sa.String(255), nullable=True),
        # field_type: number|text|date|enum|formula|boolean
        sa.Column("field_type", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(32), nullable=True),
        sa.Column("format_pattern", sa.String(64), nullable=True),
        sa.Column("enum_values", postgresql.JSONB, nullable=True),
        sa.Column("formula", sa.Text, nullable=True),
        # Scope
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="all"),
        sa.Column("scope_value", postgresql.JSONB, nullable=True),
        # Sync routing
        sa.Column("source_module", sa.String(64), nullable=True),
        sa.Column("source_path", sa.String(255), nullable=True),
        # Permissions
        sa.Column("permission_view", sa.String(128), nullable=True),
        sa.Column("permission_edit", sa.String(128), nullable=True),
        # Meta
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="100"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_field_definitions_code", "field_definitions", ["code"])
    op.create_index("ix_field_definitions_scope", "field_definitions", ["scope_type"])
    op.create_index("ix_field_definitions_source", "field_definitions", ["source_module"])

    # ── 3. company_library_views (per-user column prefs) ───────────────
    op.create_table(
        "company_library_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("visible_columns", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("filters", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("sort_by", sa.String(64), nullable=True),
        sa.Column("sort_dir", sa.String(8), nullable=False, server_default="desc"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_library_views_user", "company_library_views", ["user_id"])

    # ── 4. company_library_tabs (global tabs, system + custom) ─────────
    op.create_table(
        "company_library_tabs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column("name_uz", sa.String(255), nullable=True),
        sa.Column("name_en", sa.String(255), nullable=True),
        sa.Column("field_codes", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("layout", sa.String(32), nullable=False, server_default="two_col"),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="100"),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="all"),
        sa.Column("scope_value", postgresql.JSONB, nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_library_tabs_code", "company_library_tabs", ["code"])

    # ── 5. Seed system field_definitions ───────────────────────────────
    op.execute(r"""
        INSERT INTO field_definitions
            (code, name_ru, field_type, unit, scope_type, scope_value,
             source_module, source_path, is_system, sort_order)
        VALUES
            ('name_ru',      'Название',           'text',    NULL,     'all', NULL, 'companies', 'name_ru',       TRUE, 10),
            ('name_short',   'Короткое имя',       'text',    NULL,     'all', NULL, 'companies', 'name_short',    TRUE, 15),
            ('inn',          'ИНН',                'text',    NULL,     'all', NULL, 'companies', 'inn',           TRUE, 20),
            ('sector',       'Сектор',             'enum',    NULL,     'all', NULL, 'companies', 'sector_id',     TRUE, 30),
            ('region',       'Регион',             'text',    NULL,     'all', NULL, 'companies', 'region',        TRUE, 35),
            ('employees',    'Сотрудников',        'number',  'чел.',   'all', NULL, 'companies', 'employees_count', TRUE, 40),
            ('founded_year', 'Год основания',      'number',  NULL,     'all', NULL, 'companies', 'founded_year',  TRUE, 50),

            ('revenue',         'Выручка',         'number',  'млрд UZS', 'all', NULL, 'finmodel', 'pl.revenue',     TRUE, 100),
            ('ebitda',          'EBITDA',          'number',  'млрд UZS', 'all', NULL, 'finmodel', 'pl.ebitda',      TRUE, 110),
            ('net_profit',      'Чистая прибыль',  'number',  'млрд UZS', 'all', NULL, 'finmodel', 'pl.profit',      TRUE, 120),
            ('total_debt',      'Долг',            'number',  'млрд UZS', 'all', NULL, 'finmodel', 'bs.debt',        TRUE, 130),
            ('debt_to_ebitda',  'Долг / EBITDA',   'number',  '×',        'all', NULL, 'finmodel', 'pl.debt_to_ebitda', TRUE, 140),
            ('total_assets',    'Активы',          'number',  'млрд UZS', 'all', NULL, 'finmodel', 'bs.totalAssets', TRUE, 150),

            ('kpi_completion',  'KPI выполнение',  'number',  '%',        'all', NULL, 'kpi',      'completion',     TRUE, 200),

            ('rating_fitch',    'Fitch',           'enum',    NULL,       'all', NULL, 'ratings',  'fitch',          TRUE, 300),
            ('rating_sp',       'S&P',             'enum',    NULL,       'all', NULL, 'ratings',  'sp',             TRUE, 310),
            ('rating_moodys',   'Moody''s',        'enum',    NULL,       'all', NULL, 'ratings',  'moodys',         TRUE, 320),
            ('rating_esg',      'ESG · Sustainable Fitch', 'enum', NULL,  'all', NULL, 'ratings',  'esg',            TRUE, 330)
    """)

    # Sector-scoped examples (skip JSONB literal complexity in raw SQL — use jsonb_build_array)
    op.execute(r"""
        INSERT INTO field_definitions
            (code, name_ru, field_type, unit, scope_type, scope_value, is_system, sort_order)
        VALUES
            ('au_equivalent',     'Au-эквивалент',      'number', 'т/год',
                'sector', jsonb_build_array('mining'),           TRUE, 500),
            ('gas_production_m3', 'Добыча газа',        'number', 'млрд м³',
                'sector', jsonb_build_array('oil_gas'),          TRUE, 510),
            ('power_capacity_mw', 'Установленная мощность', 'number', 'МВт',
                'sector', jsonb_build_array('energy'),           TRUE, 520),
            ('cargo_volume_t',    'Грузоперевозки',     'number', 'млн т/год',
                'sector', jsonb_build_array('transport'),        TRUE, 530)
    """)

    # ── 6. Seed system tabs ────────────────────────────────────────────
    op.execute(r"""
        INSERT INTO company_library_tabs (code, name_ru, field_codes, layout, is_system, sort_order)
        VALUES
            ('overview',   'Обзор',          jsonb_build_array('name_ru','name_short','inn','sector','region','employees','founded_year'), 'two_col', TRUE, 10),
            ('financials', 'Финансы',        jsonb_build_array('revenue','ebitda','net_profit','total_debt','debt_to_ebitda','total_assets'), 'grid', TRUE, 20),
            ('kpi',        'KPI · BP',       jsonb_build_array('kpi_completion'),    'two_col', TRUE, 30),
            ('ratings',    'Рейтинги',       jsonb_build_array('rating_fitch','rating_sp','rating_moodys','rating_esg'), 'grid', TRUE, 40)
    """)


def downgrade() -> None:
    op.drop_index("ix_company_library_tabs_code", table_name="company_library_tabs")
    op.drop_table("company_library_tabs")
    op.drop_index("ix_company_library_views_user", table_name="company_library_views")
    op.drop_table("company_library_views")
    op.drop_index("ix_field_definitions_source", table_name="field_definitions")
    op.drop_index("ix_field_definitions_scope", table_name="field_definitions")
    op.drop_index("ix_field_definitions_code", table_name="field_definitions")
    op.drop_table("field_definitions")
    op.drop_column("companies", "custom_data")
