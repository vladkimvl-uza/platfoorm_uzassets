"""External APIs registry (Pack 12.2).

Revision ID: 9a8_external_apis
Revises: 9a7_webhooks
Create Date: 20260513-0050

Adds:
  1. external_api — registry of upstream APIs the platform consumes
  2. permissions external_apis.read / external_apis.manage seeded
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a8_external_apis"
down_revision = "9a7_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_api",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("slug", sa.String(96),  nullable=False, unique=True),  # short identifier: "openinfo", "sap_erp"
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        sa.Column("base_url",         sa.String(1024), nullable=False),
        sa.Column("documentation_url", sa.String(1024), nullable=True),
        sa.Column("health_check_url", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),  # active|sandbox|deprecated|disabled

        # Ownership / metadata
        sa.Column("owner_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contacts",   postgresql.JSONB, nullable=True),  # list of {name, email, phone, role}
        sa.Column("tags",       postgresql.JSONB, nullable=True),  # ["finance", "government", "weekly"]
        sa.Column("environment_kind", sa.String(32), nullable=True),  # production|sandbox|on-prem

        # Auth model — descriptive, NOT the actual secrets
        sa.Column("auth_kind",     sa.String(32),  nullable=True),  # oauth2|api_key|basic|mtls|none
        sa.Column("auth_details",  postgresql.JSONB, nullable=True),  # documentation: e.g. {token_url, scopes_required, credentials_vault_ref}

        # Uploaded OpenAPI spec
        sa.Column("openapi_spec",         postgresql.JSONB, nullable=True),
        sa.Column("openapi_spec_version", sa.String(32),    nullable=True),
        sa.Column("openapi_uploaded_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("openapi_uploaded_by_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Free-form notes / runbook
        sa.Column("notes", sa.Text, nullable=True),

        # Cached counts for list view (computed from spec at upload time)
        sa.Column("endpoint_count", sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.ForeignKeyConstraint(["owner_id"],                ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"],           ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["openapi_uploaded_by_id"],  ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ext_api_slug",   "external_api", ["slug"])
    op.create_index("ix_ext_api_status", "external_api", ["status"])
    op.create_index("ix_ext_api_owner",  "external_api", ["owner_id"])

    # Permissions
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'external_apis.read',   'Внешние API: просмотр',   'external_apis', 'read',
             'Просматривать реестр внешних API и их спецификации',
             now(), now()),
            (gen_random_uuid(), 'external_apis.manage', 'Внешние API: управление', 'external_apis', 'manage',
             'Регистрировать и обновлять записи внешних API, загружать OpenAPI',
             now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('external_apis.read', 'external_apis.manage')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('external_apis.read', 'external_apis.manage')")
    op.drop_index("ix_ext_api_owner",  table_name="external_api")
    op.drop_index("ix_ext_api_status", table_name="external_api")
    op.drop_index("ix_ext_api_slug",   table_name="external_api")
    op.drop_table("external_api")
