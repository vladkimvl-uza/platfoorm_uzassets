"""Admin Broadcasts (Pack 11.2).

Revision ID: 9a5_admin_broadcasts
Revises: 9a4_moderation
Create Date: 20260513-0010

Adds:
  1. admin_broadcast_template — recurring/one-shot broadcast definitions
  2. admin_broadcast_dispatch — per-execution records with stats
  3. admin_broadcast_ack      — per-recipient acknowledgement responses
  4. notification table extensions: requires_ack, ack_mode, is_sticky, etc.
  5. permission notifications.broadcast
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a5_admin_broadcasts"
down_revision = "9a4_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. admin_broadcast_template ─────
    op.create_table(
        "admin_broadcast_template",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",   sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",   sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Identification
        sa.Column("name",         sa.String(255), nullable=False),
        sa.Column("is_active",    sa.Boolean,     nullable=False, server_default=sa.text("true")),

        # Content
        sa.Column("type",       sa.String(32),  nullable=False, server_default=sa.text("'announcement'")),
        sa.Column("priority",   sa.String(16),  nullable=False, server_default=sa.text("'normal'")),
        sa.Column("title",      sa.String(255), nullable=False),
        sa.Column("body",       sa.Text,        nullable=True),
        sa.Column("link_url",   sa.String(512), nullable=True),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column("icon",       sa.String(64),  nullable=True),
        sa.Column("color",      sa.String(16),  nullable=True),

        # Targeting (resolved at each dispatch)
        sa.Column("target_user_ids",       postgresql.JSONB, nullable=True),
        sa.Column("target_group_codes",    postgresql.JSONB, nullable=True),
        sa.Column("target_role_codes",     postgresql.JSONB, nullable=True),
        sa.Column("target_company_ids",    postgresql.JSONB, nullable=True),
        sa.Column("target_sector_ids",     postgresql.JSONB, nullable=True),
        sa.Column("target_all",            sa.Boolean,      nullable=False, server_default=sa.text("false")),
        sa.Column("target_filter_expr",    postgresql.JSONB, nullable=True),

        # Acknowledgement
        sa.Column("ack_mode",         sa.String(16), nullable=False, server_default=sa.text("'none'")),
        # none | click | text | select | yesno | file
        sa.Column("ack_question",     sa.Text,       nullable=True),
        sa.Column("ack_options",      postgresql.JSONB, nullable=True),
        sa.Column("is_sticky",        sa.Boolean,    nullable=False, server_default=sa.text("false")),
        sa.Column("ack_deadline_hours", sa.Integer,  nullable=True),
        sa.Column("auto_resend_hours",   sa.Integer, nullable=True),
        sa.Column("escalate_to_manager", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("show_site_banner_on_overdue", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Schedule
        sa.Column("schedule_mode",    sa.String(16), nullable=False, server_default=sa.text("'oneshot'")),
        # oneshot | interval | cron
        sa.Column("schedule_config",  postgresql.JSONB, nullable=True),
        # {every_weeks:1, weekdays:[5], time:'09:00', tz:'Asia/Tashkent', every_days:1, every_months:1}
        sa.Column("schedule_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schedule_end_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at",       sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at",       sa.DateTime(timezone=True), nullable=True),

        # Aggregate stats
        sa.Column("total_dispatches",          sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_recipients_lifetime", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_acks_lifetime",       sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_brtpl_active_next", "admin_broadcast_template", ["is_active", "next_run_at"])
    op.create_index("ix_brtpl_creator",     "admin_broadcast_template", ["created_by_id"])

    # ───── 2. admin_broadcast_dispatch ─────
    op.create_table(
        "admin_broadcast_dispatch",
        sa.Column("id",           postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("recipients_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("delivered_count",  sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("read_count",       sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("acked_count",      sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.Column("dispatched_by_id", postgresql.UUID(as_uuid=True), nullable=True),  # null = scheduler

        sa.Column("trigger",  sa.String(16), nullable=False, server_default=sa.text("'schedule'")),
        # schedule | manual | resend
        sa.Column("error",   sa.Text, nullable=True),

        sa.ForeignKeyConstraint(["template_id"],     ["admin_broadcast_template.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dispatched_by_id"], ["users.id"],                   ondelete="SET NULL"),
    )
    op.create_index("ix_brdsp_template_time", "admin_broadcast_dispatch", ["template_id", "dispatched_at"])

    # ───── 3. admin_broadcast_ack ─────
    op.create_table(
        "admin_broadcast_ack",
        sa.Column("id",              postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dispatch_id",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_id",     postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id",         postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("acknowledged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("response_text",   sa.Text,           nullable=True),
        sa.Column("response_value",  sa.String(255),    nullable=True),
        sa.Column("response_file",   postgresql.JSONB,  nullable=True),

        sa.ForeignKeyConstraint(["notification_id"], ["notification.id"],          ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dispatch_id"],     ["admin_broadcast_dispatch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["template_id"],     ["admin_broadcast_template.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"],         ["users.id"],                  ondelete="CASCADE"),
        sa.UniqueConstraint("notification_id", name="uq_brack_notif"),
    )
    op.create_index("ix_brack_user_time",     "admin_broadcast_ack", ["user_id", "acknowledged_at"])
    op.create_index("ix_brack_template_time", "admin_broadcast_ack", ["template_id", "acknowledged_at"])

    # ───── 4. Extend notification table ─────
    op.add_column("notification", sa.Column("broadcast_template_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("notification", sa.Column("broadcast_dispatch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("notification", sa.Column("requires_ack",   sa.Boolean,      nullable=False, server_default=sa.text("false")))
    op.add_column("notification", sa.Column("ack_mode",       sa.String(16),   nullable=True))
    op.add_column("notification", sa.Column("ack_question",   sa.Text,         nullable=True))
    op.add_column("notification", sa.Column("ack_options",    postgresql.JSONB, nullable=True))
    op.add_column("notification", sa.Column("is_sticky",      sa.Boolean,      nullable=False, server_default=sa.text("false")))
    op.add_column("notification", sa.Column("ack_deadline",   sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notification", sa.Column("ack_response",   postgresql.JSONB, nullable=True))
    op.add_column("notification", sa.Column("show_site_banner", sa.Boolean, nullable=False, server_default=sa.text("false")))

    op.create_foreign_key(
        "fk_notif_broadcast_template", "notification", "admin_broadcast_template",
        ["broadcast_template_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_notif_broadcast_dispatch", "notification", "admin_broadcast_dispatch",
        ["broadcast_dispatch_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_notif_sticky_unacked", "notification",
                    ["recipient_user_id", "is_sticky", "acknowledged_at"])

    # ───── 5. Seed permission ─────
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'notifications.broadcast', 'Уведомления: рассылка',
             'notifications', 'broadcast', 'Создавать и отправлять admin broadcasts всем/группам/ролям',
             now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin' AND p.code = 'notifications.broadcast'
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code = 'notifications.broadcast'")
    op.drop_index("ix_notif_sticky_unacked", table_name="notification")
    op.drop_constraint("fk_notif_broadcast_dispatch", "notification", type_="foreignkey")
    op.drop_constraint("fk_notif_broadcast_template", "notification", type_="foreignkey")
    for c in ("show_site_banner", "ack_response", "acknowledged_at", "ack_deadline",
              "is_sticky", "ack_options", "ack_question", "ack_mode", "requires_ack",
              "broadcast_dispatch_id", "broadcast_template_id"):
        op.drop_column("notification", c)

    op.drop_index("ix_brack_template_time", table_name="admin_broadcast_ack")
    op.drop_index("ix_brack_user_time",     table_name="admin_broadcast_ack")
    op.drop_table("admin_broadcast_ack")

    op.drop_index("ix_brdsp_template_time", table_name="admin_broadcast_dispatch")
    op.drop_table("admin_broadcast_dispatch")

    op.drop_index("ix_brtpl_creator",     table_name="admin_broadcast_template")
    op.drop_index("ix_brtpl_active_next", table_name="admin_broadcast_template")
    op.drop_table("admin_broadcast_template")
