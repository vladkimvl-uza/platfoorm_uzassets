"""API Foundation (Pack 12.0).

Revision ID: 9a6_api_foundation
Revises: 9a5_admin_broadcasts
Create Date: 20260513-0011

Adds:
  1. users.is_service_account + service_account_description + service_account_owner_id
  2. audit_log.api_key_id (FK)
  3. api_key table (token hash, scopes, expiry, environment, rate limit, IP allowlist)
  4. permissions api_keys.read / api_keys.manage seeded
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a6_api_foundation"
down_revision = "9a5_admin_broadcasts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. users: service-account flags ─────
    op.add_column("users", sa.Column("is_service_account", sa.Boolean,
                                     nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("service_account_description", sa.Text, nullable=True))
    op.add_column("users", sa.Column("service_account_owner_id",
                                     postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_users_sa_owner", "users", "users",
        ["service_account_owner_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_users_is_service_account", "users", ["is_service_account"])

    # ───── 2. api_key table ─────
    op.create_table(
        "api_key",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        # Owner — the service account user this key authenticates as
        sa.Column("service_account_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Human who created the key (for audit)
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Identification
        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.Text,        nullable=True),

        # Token cryptography. prefix shown in lists. Full token shown ONCE at creation,
        # then only HMAC-SHA256(secret_key + token) stored, so we can verify but never recover.
        sa.Column("prefix",   sa.String(32),  nullable=False, unique=True),
        sa.Column("hash_hmac", sa.String(128), nullable=False),

        # Scopes — list of permission codes this key is allowed to invoke.
        sa.Column("scopes", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),

        # Environment / safety controls
        sa.Column("environment",  sa.String(16),  nullable=False, server_default=sa.text("'sandbox'")),  # production | sandbox
        sa.Column("rate_limit_per_minute", sa.Integer, nullable=False, server_default=sa.text("600")),
        sa.Column("ip_allowlist", postgresql.JSONB, nullable=True),  # ["1.2.3.0/24", ...]

        # Lifecycle
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoke_reason", sa.Text, nullable=True),

        # Telemetry
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", postgresql.INET, nullable=True),
        sa.Column("total_calls", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("failed_calls", sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.ForeignKeyConstraint(["service_account_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"],     ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_id"],     ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_apikey_sa",          "api_key", ["service_account_id"])
    op.create_index("ix_apikey_revoked",     "api_key", ["revoked_at"])
    op.create_index("ix_apikey_expires",     "api_key", ["expires_at"])
    op.create_index("ix_apikey_prefix",      "api_key", ["prefix"])

    # ───── 3. audit_log.api_key_id ─────
    op.add_column("audit_log", sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_audit_log_api_key", "audit_log", "api_key",
        ["api_key_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_audit_log_api_key", "audit_log", ["api_key_id"])

    # ───── 4. Seed permissions ─────
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'api_keys.read',   'API ключи: просмотр',  'api_keys', 'read',
             'Просматривать список и метаданные API ключей',
             now(), now()),
            (gen_random_uuid(), 'api_keys.manage', 'API ключи: управление', 'api_keys', 'manage',
             'Выпускать, отзывать и редактировать API ключи / service accounts',
             now(), now()),
            (gen_random_uuid(), 'api_catalog.read', 'API каталог: просмотр', 'api_catalog', 'read',
             'Просматривать каталог API endpoints и скачивать OpenAPI спецификации',
             now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('api_keys.read', 'api_keys.manage', 'api_catalog.read')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('api_keys.read','api_keys.manage','api_catalog.read')")

    op.drop_index("ix_audit_log_api_key", table_name="audit_log")
    op.drop_constraint("fk_audit_log_api_key", "audit_log", type_="foreignkey")
    op.drop_column("audit_log", "api_key_id")

    for ix in ("ix_apikey_prefix","ix_apikey_expires","ix_apikey_revoked","ix_apikey_sa"):
        op.drop_index(ix, table_name="api_key")
    op.drop_table("api_key")

    op.drop_index("ix_users_is_service_account", table_name="users")
    op.drop_constraint("fk_users_sa_owner", "users", type_="foreignkey")
    for c in ("service_account_owner_id", "service_account_description", "is_service_account"):
        op.drop_column("users", c)
