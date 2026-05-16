"""Webhooks (Pack 12.1).

Revision ID: 9a7_webhooks
Revises: 9a6_api_foundation
Create Date: 20260513-0030

Adds:
  1. webhook_subscription — per-SA subscriptions to platform events
  2. webhook_delivery     — delivery log with retry state machine
  3. permissions webhooks.read / webhooks.manage seeded
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a7_webhooks"
down_revision = "9a6_api_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. webhook_subscription ─────
    op.create_table(
        "webhook_subscription",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("service_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_id",      postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.Text,        nullable=True),

        # Target
        sa.Column("target_url",  sa.String(1024), nullable=False),
        sa.Column("secret_hint", sa.String(16),   nullable=False),    # last 8 chars of secret for display
        sa.Column("secret_hash", sa.String(128),  nullable=False),    # HMAC of the secret with server key (for verify only)
        sa.Column("secret_plain", sa.Text,        nullable=False),    # the actual secret used to sign deliveries
                                                                       # (encrypted-at-rest in prod via PG TDE / volume encryption)
        sa.Column("verify_ssl",  sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("custom_headers", postgresql.JSONB, nullable=True),  # dict of extra headers

        # Subscriptions
        sa.Column("events", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),  # list of event codes / wildcards

        # Lifecycle
        sa.Column("is_active",   sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_reason", sa.Text, nullable=True),

        # Retry policy
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default=sa.text("5")),
        sa.Column("timeout_seconds", sa.Integer, nullable=False, server_default=sa.text("10")),

        # Telemetry
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_deliveries", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_failures",   sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.ForeignKeyConstraint(["service_account_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"],      ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wh_sub_sa",      "webhook_subscription", ["service_account_id"])
    op.create_index("ix_wh_sub_active",  "webhook_subscription", ["is_active"])

    # ───── 2. webhook_delivery ─────
    op.create_table(
        "webhook_delivery",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_code",      sa.String(128), nullable=False),
        sa.Column("event_payload",   postgresql.JSONB, nullable=False),
        sa.Column("correlation_id",  postgresql.UUID(as_uuid=True), nullable=True),  # group related deliveries

        # State machine: pending → succeeded | failed | exhausted | cancelled
        sa.Column("status",          sa.String(16),  nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempt_number",  sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("scheduled_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("attempted_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at",    sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at",   sa.DateTime(timezone=True), nullable=True),

        # Signing
        sa.Column("signature",       sa.String(128), nullable=True),  # the HMAC we sent on attempt N
        sa.Column("timestamp_sent",  sa.BigInteger,  nullable=True),

        # Response
        sa.Column("http_status",         sa.Integer, nullable=True),
        sa.Column("response_body_snippet", sa.Text,  nullable=True),  # first 4KB of body
        sa.Column("response_headers_snippet", postgresql.JSONB, nullable=True),  # selected headers
        sa.Column("error_message",      sa.Text, nullable=True),
        sa.Column("duration_ms",        sa.Integer, nullable=True),

        # Replay control
        sa.Column("is_replay",       sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("replay_of_id",    postgresql.UUID(as_uuid=True), nullable=True),

        sa.ForeignKeyConstraint(["subscription_id"], ["webhook_subscription.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replay_of_id"],    ["webhook_delivery.id"],    ondelete="SET NULL"),
    )
    op.create_index("ix_wh_del_sub_time",   "webhook_delivery", ["subscription_id", "created_at"])
    op.create_index("ix_wh_del_status",     "webhook_delivery", ["status"])
    op.create_index("ix_wh_del_event",      "webhook_delivery", ["event_code", "created_at"])
    # Critical: worker poller index — find all deliveries ready to send
    op.create_index("ix_wh_del_poller",     "webhook_delivery", ["status", "scheduled_at"],
                    postgresql_where=sa.text("status = 'pending'"))

    # ───── 3. Seed permissions ─────
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'webhooks.read',   'Webhooks: просмотр',   'webhooks', 'read',
             'Просматривать подписки webhook и журналы доставки',
             now(), now()),
            (gen_random_uuid(), 'webhooks.manage', 'Webhooks: управление', 'webhooks', 'manage',
             'Создавать, изменять и удалять подписки webhook',
             now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin'
          AND p.code IN ('webhooks.read', 'webhooks.manage')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('webhooks.read', 'webhooks.manage')")
    op.drop_index("ix_wh_del_poller",   table_name="webhook_delivery")
    op.drop_index("ix_wh_del_event",    table_name="webhook_delivery")
    op.drop_index("ix_wh_del_status",   table_name="webhook_delivery")
    op.drop_index("ix_wh_del_sub_time", table_name="webhook_delivery")
    op.drop_table("webhook_delivery")
    op.drop_index("ix_wh_sub_active",   table_name="webhook_subscription")
    op.drop_index("ix_wh_sub_sa",       table_name="webhook_subscription")
    op.drop_table("webhook_subscription")
