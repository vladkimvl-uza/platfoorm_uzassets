"""Moderation system tables (Pack 11.1).

Revision ID: 9a4_moderation
Revises: 9a3_notifications
Create Date: 20260512-2345

Adds:
  1. moderation_submission — proposed changes pending review
  2. moderation_comment    — discussion thread per submission
  3. moderation_rule       — flexible matchers: WHO + WHAT + WHERE + ACTION + THRESHOLD → moderator chain
  4. seed moderation.* permissions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9a4_moderation"
down_revision = "9a3_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ───── 1. moderation_submission ─────
    op.create_table(
        "moderation_submission",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        # Proposer
        sa.Column("proposer_user_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposer_is_external", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Target
        sa.Column("target_module",       sa.String(64),  nullable=False),
        sa.Column("target_entity_id",    sa.String(128), nullable=True),
        sa.Column("target_entity_label", sa.String(255), nullable=True),  # human-readable
        sa.Column("target_field",        sa.String(128), nullable=True),
        sa.Column("target_company_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_sector_id",    postgresql.UUID(as_uuid=True), nullable=True),

        # Change content
        sa.Column("action",          sa.String(32), nullable=False, server_default=sa.text("'edit'")),
        # action: edit | replace | comment | upload | delete | status_change
        sa.Column("proposed_value",  postgresql.JSONB, nullable=True),
        sa.Column("original_value",  postgresql.JSONB, nullable=True),
        sa.Column("diff_summary",    sa.Text, nullable=True),
        sa.Column("attachments",     postgresql.JSONB, nullable=True),
        sa.Column("reason",          sa.Text, nullable=True),  # proposer's justification

        # Status
        sa.Column("status", sa.String(24), nullable=False, server_default=sa.text("'pending'")),
        # status: pending | under_review | approved | rejected | withdrawn | expired

        # Moderation chain
        sa.Column("rule_id",                 postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_moderator_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("coapprover_id",           postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewer_ids",            postgresql.JSONB, nullable=True),
        sa.Column("approval_mode",           sa.String(16), nullable=False, server_default=sa.text("'any'")),
        # approval_mode: any | dual | sequential
        sa.Column("approvals_given",         postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        # list of {user_id, at} who already approved (for dual mode)

        # Resolution
        sa.Column("resolved_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_note",  sa.Text, nullable=True),
        sa.Column("auto_resolved",    sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Lifecycle
        sa.Column("expires_at",          sa.DateTime(timezone=True), nullable=True),
        sa.Column("escalated_at",        sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at",    sa.DateTime(timezone=True), nullable=True),

        # Trace
        sa.Column("source_ip",       sa.String(45), nullable=True),
        sa.Column("source_user_agent", sa.String(512), nullable=True),

        sa.ForeignKeyConstraint(["proposer_user_id"],     ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_moderator_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["coapprover_id"],         ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"],        ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_company_id"],     ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_sector_id"],      ["sectors.id"],  ondelete="SET NULL"),
    )
    op.create_index("ix_modsub_status_created", "moderation_submission", ["status", "created_at"])
    op.create_index("ix_modsub_moderator",      "moderation_submission", ["assigned_moderator_id", "status"])
    op.create_index("ix_modsub_proposer",       "moderation_submission", ["proposer_user_id", "created_at"])
    op.create_index("ix_modsub_module",         "moderation_submission", ["target_module", "status"])

    # ───── 2. moderation_comment ─────
    op.create_table(
        "moderation_comment",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id",       postgresql.UUID(as_uuid=True), nullable=False),

        sa.Column("text",        sa.Text, nullable=False),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column("is_internal", sa.Boolean, nullable=False, server_default=sa.text("false")),  # moderator-only

        sa.ForeignKeyConstraint(["submission_id"], ["moderation_submission.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"],       ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_modcom_submission_created", "moderation_comment", ["submission_id", "created_at"])

    # ───── 3. moderation_rule ─────
    op.create_table(
        "moderation_rule",
        sa.Column("id",          postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at",  sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("name",         sa.String(255), nullable=False),
        sa.Column("description",  sa.Text, nullable=True),
        sa.Column("icon",         sa.String(64), nullable=True),
        sa.Column("is_active",    sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order",   sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column("version",      sa.Integer, nullable=False, server_default=sa.text("1")),

        # ─── WHO triggers ───
        sa.Column("trigger_user_ids",     postgresql.JSONB, nullable=True),
        sa.Column("trigger_group_codes",  postgresql.JSONB, nullable=True),
        sa.Column("trigger_role_codes",   postgresql.JSONB, nullable=True),
        sa.Column("trigger_is_external",  sa.Boolean, nullable=False, server_default=sa.text("false")),

        # ─── WHAT ───
        sa.Column("trigger_modules", postgresql.JSONB, nullable=True),  # ['kpi','financials',...]

        # ─── WHERE ───
        sa.Column("trigger_company_ids", postgresql.JSONB, nullable=True),
        sa.Column("trigger_sector_ids",  postgresql.JSONB, nullable=True),
        sa.Column("trigger_year_from",   sa.Integer, nullable=True),
        sa.Column("trigger_year_to",     sa.Integer, nullable=True),

        # ─── ACTION ───
        sa.Column("trigger_actions", postgresql.JSONB, nullable=True),  # ['edit','replace',...]

        # ─── THRESHOLDS ───
        sa.Column("trigger_conditions", postgresql.JSONB, nullable=True),
        # [{field: 'amount', op: '>', value: 1000000, unit: 'USD'}, ...]

        # ─── Moderation chain ───
        sa.Column("moderator_primary_id",      postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("moderator_coapprover_id",   postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("moderator_fallback_group_code", sa.String(64), nullable=True),
        sa.Column("approval_mode",             sa.String(16), nullable=False, server_default=sa.text("'any'")),

        # ─── Auto-actions ───
        sa.Column("escalate_after_hours",      sa.Integer, nullable=True),
        sa.Column("auto_approve_after_hours",  sa.Integer, nullable=True),
        sa.Column("expire_after_days",         sa.Integer, nullable=False, server_default=sa.text("30")),

        # ─── Notifications ───
        sa.Column("notify_proposer_assigned", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notify_proposer_resolved", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notify_coapprovers_cc",    sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("notify_owner_on_reject",   sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("log_to_audit",             sa.Boolean, nullable=False, server_default=sa.text("true")),

        # ─── Stats ───
        sa.Column("last_matched_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_matches",     sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_approvals",   sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_rejections",  sa.Integer, nullable=False, server_default=sa.text("0")),

        sa.ForeignKeyConstraint(["created_by_id"],            ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["moderator_primary_id"],     ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["moderator_coapprover_id"],  ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_modrule_active_order", "moderation_rule", ["is_active", "sort_order"])

    # ───── 4. Seed moderation.* permissions ─────
    op.execute(sa.text("""
        INSERT INTO permissions (id, code, name, module, action, description, created_at, updated_at) VALUES
            (gen_random_uuid(), 'moderation.review', 'Модерация: проверка',      'moderation', 'review', 'Проверять и одобрять/отклонять чужие предложения', now(), now()),
            (gen_random_uuid(), 'moderation.submit', 'Модерация: предложения',   'moderation', 'submit', 'Подавать предложения на модерацию (для external/restricted)', now(), now()),
            (gen_random_uuid(), 'moderation.bypass', 'Модерация: обход',          'moderation', 'bypass', 'Обходить модерацию для своих изменений', now(), now()),
            (gen_random_uuid(), 'moderation.admin',  'Модерация: правила',        'moderation', 'admin',  'Настраивать правила модерации, модераторов', now(), now())
        ON CONFLICT (code) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO role_permission (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.code = 'admin' AND p.code IN
            ('moderation.review','moderation.bypass','moderation.admin')
        ON CONFLICT DO NOTHING
    """))


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('moderation.review','moderation.submit','moderation.bypass','moderation.admin')")
    op.drop_index("ix_modrule_active_order",    table_name="moderation_rule")
    op.drop_table("moderation_rule")
    op.drop_index("ix_modcom_submission_created", table_name="moderation_comment")
    op.drop_table("moderation_comment")
    op.drop_index("ix_modsub_module",     table_name="moderation_submission")
    op.drop_index("ix_modsub_proposer",   table_name="moderation_submission")
    op.drop_index("ix_modsub_moderator",  table_name="moderation_submission")
    op.drop_index("ix_modsub_status_created", table_name="moderation_submission")
    op.drop_table("moderation_submission")
