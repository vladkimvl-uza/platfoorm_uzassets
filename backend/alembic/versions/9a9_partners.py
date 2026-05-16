"""Integration partners + audit links (Pack 12.4).

Revision ID: 9a9_partners
Revises: 9a8_external_apis
Create Date: 20260513-0110

Adds:
  1. integration_partner — umbrella org grouping SAs / external APIs / webhooks
  2. Nullable partner_id FK on: users, external_api, webhook_subscription
  3. permissions integration_partners.read / integration_partners.manage seeded
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a9_partners"
down_revision = "9a8_external_apis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. integration_partner ─────
    op.create_table(
        "integration_partner",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("slug", sa.String(96),  nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(512), nullable=True),
        sa.Column("description", sa.Text, nullable=True),

        sa.Column("kind", sa.String(32), nullable=True),   # gov_ministry|portfolio_company|saas_vendor|bank|integrator|other
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),  # active|suspended|terminated
        sa.Column("tier",   sa.String(16), nullable=True),  # platinum|gold|silver|standard

        sa.Column("contacts", postgresql.JSONB, nullable=True),
        sa.Column("tags",     postgresql.JSONB, nullable=True),

        # Contract / agreement metadata (descriptive, not the contracts themselves)
        sa.Column("contract_ref",    sa.String(128), nullable=True),
        sa.Column("contract_start",  sa.Date,        nullable=True),
        sa.Column("contract_end",    sa.Date,        nullable=True),

        sa.Column("owner_id",       postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_id",  postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("notes", sa.Text, nullable=True),

        sa.ForeignKeyConstraint(["owner_id"],      ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_partner_slug",   "integration_partner", ["slug"])
    op.create_index("ix_partner_status", "integration_partner", ["status"])

    # ───── 2. Link tables ─────
    op.add_column("users",
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_users_partner", "users", "integration_partner",
        ["partner_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_users_partner", "users", ["partner_id"])

    op.add_column("external_api",
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_ext_api_partner", "external_api", "integration_partner",
        ["partner_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_ext_api_partner", "external_api", ["partner_id"])

    op.add_column("webhook_subscription",
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_wh_sub_partner", "webhook_subscription", "integration_partner",
        ["partner_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_wh_sub_partner", "webhook_subscription", ["partner_id"])

    # ───── 3. Permissions ─────
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'integration_partners.read',   'Партнёры: просмотр',    'integration_partners', 'read',
             'Просматривать реестр интеграционных партнёров и связанных ресурсов',
             now(), now()),
            (gen_random_uuid(), 'integration_partners.manage', 'Партнёры: управление',  'integration_partners', 'manage',
             'Регистрировать, редактировать партнёров и привязывать SA / API / webhooks',
             now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('integration_partners.read', 'integration_partners.manage')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('integration_partners.read', 'integration_partners.manage')")

    op.drop_index("ix_wh_sub_partner",  table_name="webhook_subscription")
    op.drop_constraint("fk_wh_sub_partner", "webhook_subscription", type_="foreignkey")
    op.drop_column("webhook_subscription", "partner_id")

    op.drop_index("ix_ext_api_partner", table_name="external_api")
    op.drop_constraint("fk_ext_api_partner", "external_api", type_="foreignkey")
    op.drop_column("external_api", "partner_id")

    op.drop_index("ix_users_partner",   table_name="users")
    op.drop_constraint("fk_users_partner", "users", type_="foreignkey")
    op.drop_column("users", "partner_id")

    op.drop_index("ix_partner_status",  table_name="integration_partner")
    op.drop_index("ix_partner_slug",    table_name="integration_partner")
    op.drop_table("integration_partner")
