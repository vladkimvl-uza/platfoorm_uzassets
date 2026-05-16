"""Notifications foundation + user.is_external flag (Pack 11.0).

Revision ID: 9a3_notifications
Revises: 9a2_companies_advanced
Create Date: 20260512-2330

Adds:
  1. users: is_external (bool) + requires_moderation (bool) + bypass_moderation (bool)
  2. notification table — in-app notifications
  3. notification_preference table — per-user per-type channels
  4. seed core permissions: notifications.send, notifications.admin
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a3_notifications"
down_revision = "9a2_companies_advanced"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. User flags for external + moderation ─────
    op.add_column("users", sa.Column("is_external",         sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("requires_moderation", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("bypass_moderation",   sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("users", sa.Column("external_org_name",   sa.String(255), nullable=True))
    op.create_index("ix_users_is_external", "users", ["is_external"], postgresql_where=sa.text("is_external = true"))

    # ───── 2. notification ─────
    op.create_table(
        "notification",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type",              sa.String(64),  nullable=False),
        sa.Column("priority",          sa.String(16),  nullable=False, server_default=sa.text("'normal'")),
        # priority: low | normal | high | critical

        sa.Column("title",     sa.String(255), nullable=False),
        sa.Column("body",      sa.Text,        nullable=True),
        sa.Column("payload",   postgresql.JSONB, nullable=True),

        sa.Column("link_url",  sa.String(512), nullable=True),

        sa.Column("source_module",    sa.String(64),  nullable=True),
        sa.Column("source_entity_id", sa.String(64),  nullable=True),
        sa.Column("source_user_id",   postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("is_read",     sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("read_at",     sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),

        # Delivery tracking: {in_app:true, ws_sent_at:'2026-...', email_sent_at:null, ...}
        sa.Column("delivered_channels", postgresql.JSONB, nullable=True),

        sa.Column("expires_at",  sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_user_id"],    ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notif_recipient_unread", "notification",
                    ["recipient_user_id", "is_read", "created_at"])
    op.create_index("ix_notif_recipient_created", "notification",
                    ["recipient_user_id", "created_at"])
    op.create_index("ix_notif_type",     "notification", ["type"])
    op.create_index("ix_notif_priority", "notification", ["priority"],
                    postgresql_where=sa.text("priority IN ('high','critical')"))

    # ───── 3. notification_preference ─────
    op.create_table(
        "notification_preference",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("user_id",            postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type",  sa.String(64), nullable=False),

        # Channels: {in_app:true, email:false, telegram:false, push:false}
        sa.Column("channels", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{\"in_app\": true}'::jsonb")),

        sa.Column("is_muted",   sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("mute_until", sa.DateTime(timezone=True), nullable=True),

        # digest_mode: none | daily | weekly
        sa.Column("digest_mode", sa.String(16), nullable=False, server_default=sa.text("'none'")),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "notification_type", name="uq_notif_pref"),
    )

    # ───── 4. Seed notification-related permissions ─────
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'notifications.send',  'Отправка уведомлений',   'notifications', 'send',  'Создавать уведомления для других пользователей', now(), now()),
            (gen_random_uuid(), 'notifications.admin', 'Администрирование уведомлений', 'notifications', 'admin', 'Управление system-уведомлениями и broadcast', now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin' AND p.code IN ('notifications.send','notifications.admin')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('notifications.send','notifications.admin')")

    op.drop_table("notification_preference")

    op.drop_index("ix_notif_priority",          table_name="notification")
    op.drop_index("ix_notif_type",              table_name="notification")
    op.drop_index("ix_notif_recipient_created", table_name="notification")
    op.drop_index("ix_notif_recipient_unread",  table_name="notification")
    op.drop_table("notification")

    op.drop_index("ix_users_is_external", table_name="users")
    op.drop_column("users", "external_org_name")
    op.drop_column("users", "bypass_moderation")
    op.drop_column("users", "requires_moderation")
    op.drop_column("users", "is_external")
