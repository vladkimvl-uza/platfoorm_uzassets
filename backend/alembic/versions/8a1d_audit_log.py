"""Audit log table + audit.* permissions (Pack 9.0).

Revision ID: 8a1d_audit_log
Revises: 7b2c0ffe4ai0, 7c29bd804fae
Create Date: 20260512-2100
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "8a1d_audit_log"
down_revision = ("7b2c0ffe4ai0", "7c29bd804fae")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. audit_log table (matches app/models/audit.py)
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        # who
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role",  sa.String(64),  nullable=True),

        # what
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("module", sa.String(64), nullable=True),
        sa.Column("entity_type",  sa.String(64),  nullable=True),
        sa.Column("entity_id",    sa.String(128), nullable=True),
        sa.Column("entity_label", sa.Text,        nullable=True),

        # http
        sa.Column("http_method", sa.String(10),  nullable=True),
        sa.Column("http_path",   sa.String(512), nullable=True),
        sa.Column("http_status", sa.Integer,     nullable=True),
        sa.Column("duration_ms", sa.Integer,     nullable=True),

        # diff / extras
        sa.Column("diff",    postgresql.JSONB, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("meta",    postgresql.JSONB, nullable=True),
        sa.Column("notes",   sa.Text,          nullable=True),

        # context
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("is_critical", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),

        # HMAC chain
        sa.Column("prev_hash",  sa.String(64), nullable=True),
        sa.Column("entry_hash", sa.String(64), nullable=True),

        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Single-column indexes
    op.create_index("ix_audit_log_actor_id",    "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_action",      "audit_log", ["action"])
    op.create_index("ix_audit_log_module",      "audit_log", ["module"])
    op.create_index("ix_audit_log_entity_type", "audit_log", ["entity_type"])
    op.create_index("ix_audit_log_entity_id",   "audit_log", ["entity_id"])
    op.create_index("ix_audit_log_prev_hash",   "audit_log", ["prev_hash"])
    op.create_unique_constraint("uq_audit_entry_hash", "audit_log", ["entry_hash"])

    # Composite indexes
    op.create_index("ix_audit_actor_action_time", "audit_log",
                    ["actor_id", "action", "created_at"])
    op.create_index("ix_audit_entity_time",       "audit_log",
                    ["entity_type", "entity_id", "created_at"])
    op.create_index("ix_audit_module_time",       "audit_log",
                    ["module", "created_at"])
    op.create_index("ix_audit_action_time",       "audit_log",
                    ["action", "created_at"])
    op.create_index("ix_audit_critical_time",     "audit_log",
                    ["created_at"],
                    postgresql_where=sa.text("is_critical = true"))

    # 2. Seed permissions: audit.view + audit.admin
    op.execute("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at)
        VALUES
            (gen_random_uuid(), 'audit.view',  'Просмотр журнала активности',     'audit', 'view',  'Доступ к панели аудита (журнал событий, статистика, security flags)', now(), now()),
            (gen_random_uuid(), 'audit.admin', 'Управление аудитом',              'audit', 'admin', 'Сброс security flags, экспорт CSV, настройки retention',              now(), now())
        ON CONFLICT (code) DO NOTHING;
    """)

    # 3. Grant audit.view + audit.admin to admin role (owner already bypasses)
    op.execute("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('audit.view', 'audit.admin')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permission
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE code IN ('audit.view', 'audit.admin')
        );
    """)
    op.execute("DELETE FROM permissions WHERE code IN ('audit.view', 'audit.admin');")

    for idx in [
        "ix_audit_critical_time", "ix_audit_action_time", "ix_audit_module_time",
        "ix_audit_entity_time", "ix_audit_actor_action_time",
        "uq_audit_entry_hash", "ix_audit_log_prev_hash", "ix_audit_log_entity_id",
        "ix_audit_log_entity_type", "ix_audit_log_module", "ix_audit_log_action",
        "ix_audit_log_actor_id",
    ]:
        try:
            op.drop_index(idx, table_name="audit_log")
        except Exception:
            pass

    op.drop_table("audit_log")
