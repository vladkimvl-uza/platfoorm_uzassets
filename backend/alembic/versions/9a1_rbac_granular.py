"""RBAC v2 — granular grants + groups + templates + change log (Pack 9.1).

Revision ID: 9a1_rbac_granular
Revises: fc8634ac418b
Create Date: 20260512-2200

Adds:
  1. Seed 22 missing permissions used by routes but never in catalog
  2. user_permission_grant — direct grant/deny per user with scope + expires_at
  3. user_module_visibility — per-user module hide
  4. group_permission_grant — permission grants on group level
  5. group_role — role assignments on group level
  6. permission_template — reusable permission bundles
  7. rbac_change_log — audit of every RBAC change
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a1_rbac_granular"
down_revision = "fc8634ac418b"
branch_labels = None
depends_on = None


PERMISSION_CATALOG_MISSING = [
    # (code, name, module, action, description)
    ("companies.view",          "Просмотр компаний",           "companies",   "view",   "Список + детали компаний"),
    ("companies.view_all",      "Просмотр всех компаний",      "companies",   "view",   "Доступ ко всем 22 компаниям портфеля"),
    ("companies.create",        "Создание компаний",           "companies",   "create", "Добавление новой портфельной компании"),
    ("companies.edit",          "Редактирование компаний",     "companies",   "edit",   "Изменение паспорта компании"),
    ("companies.delete",        "Удаление компаний",           "companies",   "delete", "Удаление компании из портфеля (необратимо)"),

    ("sectors.view",            "Просмотр секторов",           "sectors",     "view",   "Список секторов"),
    ("sectors.create",          "Создание секторов",           "sectors",     "create", "Добавление нового сектора"),
    ("sectors.edit",            "Редактирование секторов",     "sectors",     "edit",   "Изменение названия/цвета сектора"),
    ("sectors.delete",          "Удаление секторов",           "sectors",     "delete", "Удаление сектора"),

    ("credit.view",             "Просмотр кредитного портфеля","credit",      "view",   "Доступ к кредитам и FX"),
    ("credit.edit",             "Редактирование кредитов",     "credit",      "edit",   "Изменение записей cp_loans"),

    ("esg.view",                "Просмотр ESG",                "esg",         "view",   "Доступ к ESG-дашборду"),
    ("esg.edit",                "Редактирование ESG",          "esg",         "edit",   "Метрики, цели, инциденты ESG"),

    ("financials.view",         "Просмотр финансов",           "financials",  "view",   "Доступ к финансовым отчётам"),
    ("financials.edit",         "Редактирование финансов",     "financials",  "edit",   "Импорт и редактирование IFRS / НСБУ"),

    ("governance.view",         "Просмотр КУ",                 "governance",  "view",   "Корпоративное управление, доска"),
    ("governance.edit",         "Редактирование КУ",           "governance",  "edit",   "Состав НС, комитеты, оценки"),

    ("procurement.view",        "Просмотр закупок",            "procurement", "view",   "Закупочные тендеры и аналитика"),

    ("ratings.view",            "Просмотр рейтингов",          "ratings",     "view",   "Кредитные и ESG-рейтинги"),
    ("ratings.edit",            "Редактирование рейтингов",    "ratings",     "edit",   "Импорт рейтингов"),

    ("tasks.view",              "Просмотр задач",              "tasks",       "view",   "Канбан-доски, проекты"),
    ("tasks.edit",              "Редактирование задач",        "tasks",       "edit",   "Создание/редактирование задач"),
    ("tasks.delete",            "Удаление задач",              "tasks",       "delete", "Удаление задач (необратимо)"),
]


def upgrade() -> None:
    # ───────────── 1. Seed missing permissions ─────────────
    for code, name, module, action, desc in PERMISSION_CATALOG_MISSING:
        op.execute(sa.text("""
            INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at)
            VALUES (gen_random_uuid(), :code, :name, :module, :action, :desc, now(), now())
            ON CONFLICT (code) DO NOTHING
        """).bindparams(code=code, name=name, module=module, action=action, desc=desc))

    # Grant ALL permissions to admin role (admin should have everything)
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin'
        ON CONFLICT DO NOTHING
    """)

    # ───────────── 2. user_permission_grant ─────────────
    op.create_table(
        "user_permission_grant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("user_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_code", sa.String(128), nullable=False),
        # 'grant' (positive) or 'deny' (explicit revoke that overrides role)
        sa.Column("grant_type",     sa.String(16), nullable=False, server_default=sa.text("'grant'")),

        # Scope filters (NULL = no restriction)
        sa.Column("scope_companies", postgresql.JSONB, nullable=True),   # array of company codes
        sa.Column("scope_sectors",   postgresql.JSONB, nullable=True),   # array of sector codes
        sa.Column("scope_years",     postgresql.JSONB, nullable=True),   # array of int years

        # Time-bound access
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("granted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason",        sa.String(512), nullable=True),

        sa.ForeignKeyConstraint(["user_id"],        ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"],  ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", "permission_code", name="uq_user_perm_grant"),
    )
    op.create_index("ix_upg_user", "user_permission_grant", ["user_id"])
    op.create_index("ix_upg_code", "user_permission_grant", ["permission_code"])
    op.create_index("ix_upg_expires", "user_permission_grant", ["expires_at"],
                    postgresql_where=sa.text("expires_at IS NOT NULL"))

    # ───────────── 3. user_module_visibility ─────────────
    op.create_table(
        "user_module_visibility",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("user_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_code", sa.String(64), nullable=False),
        sa.Column("is_visible",  sa.Boolean, nullable=False, server_default=sa.text("true")),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "module_code", name="uq_user_module_vis"),
    )
    op.create_index("ix_umv_user", "user_module_visibility", ["user_id"])

    # ───────────── 4. group_permission_grant ─────────────
    op.create_table(
        "group_permission_grant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("group_id",        postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_code", sa.String(128), nullable=False),
        sa.Column("grant_type",      sa.String(16), nullable=False, server_default=sa.text("'grant'")),

        sa.Column("scope_companies", postgresql.JSONB, nullable=True),
        sa.Column("scope_sectors",   postgresql.JSONB, nullable=True),
        sa.Column("scope_years",     postgresql.JSONB, nullable=True),
        sa.Column("expires_at",      sa.DateTime(timezone=True), nullable=True),

        sa.Column("granted_by_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.ForeignKeyConstraint(["group_id"],      ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"],  ondelete="SET NULL"),
        sa.UniqueConstraint("group_id", "permission_code", name="uq_group_perm_grant"),
    )
    op.create_index("ix_gpg_group", "group_permission_grant", ["group_id"])

    # ───────────── 5. group_role ─────────────
    op.create_table(
        "group_role",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("role_id",  postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"],  ["roles.id"],  ondelete="CASCADE"),
    )

    # ───────────── 6. permission_template ─────────────
    op.create_table(
        "permission_template",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("code",        sa.String(64), unique=True, nullable=False),
        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("category",    sa.String(64), nullable=True),

        sa.Column("permissions",     postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("module_visibility", postgresql.JSONB, nullable=True),
        sa.Column("scope_defaults",  postgresql.JSONB, nullable=True),

        sa.Column("is_system", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Seed 4 starter templates (system, non-editable)
    op.execute("""
        INSERT INTO permission_template (id, code, name, description, category, permissions, is_system, created_at, updated_at)
        VALUES
            (gen_random_uuid(), 'tmpl_view_only',  'Только просмотр',
             'Все модули — только view, без редактирования и удаления',  'базовый',
             '["kpi.view","bp.view","governance.view","esg.view","financials.view","procurement.view","ratings.view","companies.view","tasks.view"]'::jsonb,
             true, now(), now()),

            (gen_random_uuid(), 'tmpl_financier', 'Финансовый аналитик',
             'Финансы + KPI + БП на view+edit, остальное view',           'специалист',
             '["kpi.view","kpi.edit","bp.view","bp.edit","financials.view","financials.edit","credit.view","governance.view","esg.view","ratings.view"]'::jsonb,
             true, now(), now()),

            (gen_random_uuid(), 'tmpl_governance', 'Корп. управление',
             'Governance + ESG + Ratings на edit, прочее view',           'специалист',
             '["governance.view","governance.edit","esg.view","esg.edit","ratings.view","ratings.edit","kpi.view","bp.view","companies.view"]'::jsonb,
             true, now(), now()),

            (gen_random_uuid(), 'tmpl_dept_head', 'Руководитель отдела',
             'Все модули view + tasks edit + БП edit',                    'руководитель',
             '["kpi.view","bp.view","bp.edit","governance.view","esg.view","financials.view","procurement.view","ratings.view","companies.view","tasks.view","tasks.edit"]'::jsonb,
             true, now(), now())
        ON CONFLICT (code) DO NOTHING
    """)

    # ───────────── 7. rbac_change_log ─────────────
    op.create_table(
        "rbac_change_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("change_type", sa.String(32), nullable=False),
        # types: grant_added | grant_removed | grant_modified | role_assigned | role_removed |
        #        visibility_changed | template_applied | group_created | group_perm_changed |
        #        owner_assigned | owner_revoked | user_created | user_disabled

        sa.Column("subject_user_id",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject_email",    sa.String(255), nullable=True),

        sa.Column("changed_by_id",    postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_by_email", sa.String(255), nullable=True),

        sa.Column("before_state", postgresql.JSONB, nullable=True),
        sa.Column("after_state",  postgresql.JSONB, nullable=True),
        sa.Column("summary",      sa.String(512), nullable=True),

        sa.ForeignKeyConstraint(["subject_user_id"],  ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subject_group_id"], ["groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["changed_by_id"],    ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_rcl_subject", "rbac_change_log", ["subject_user_id", "created_at"])
    op.create_index("ix_rcl_type_time", "rbac_change_log", ["change_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_rcl_type_time", table_name="rbac_change_log")
    op.drop_index("ix_rcl_subject",   table_name="rbac_change_log")
    op.drop_table("rbac_change_log")

    op.drop_table("permission_template")
    op.drop_table("group_role")

    op.drop_index("ix_gpg_group",     table_name="group_permission_grant")
    op.drop_table("group_permission_grant")

    op.drop_index("ix_umv_user",      table_name="user_module_visibility")
    op.drop_table("user_module_visibility")

    op.drop_index("ix_upg_expires",   table_name="user_permission_grant")
    op.drop_index("ix_upg_code",      table_name="user_permission_grant")
    op.drop_index("ix_upg_user",      table_name="user_permission_grant")
    op.drop_table("user_permission_grant")

    op.execute("""
        DELETE FROM permissions WHERE code IN (
            'companies.view','companies.view_all','companies.create','companies.edit','companies.delete',
            'sectors.view','sectors.create','sectors.edit','sectors.delete',
            'credit.view','credit.edit',
            'esg.view','esg.edit',
            'financials.view','financials.edit',
            'governance.view','governance.edit',
            'procurement.view',
            'ratings.view','ratings.edit',
            'tasks.view','tasks.edit','tasks.delete'
        )
    """)
