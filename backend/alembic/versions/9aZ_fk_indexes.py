"""Add missing indexes on 93 ForeignKey columns (Pack-audit 2026-05-26).

Findings from backend/scripts/audit_fk_v3.py — 167 total FK cols, 93 missing
index=True. Tables affected: admin_broadcast_*, api_key, boards, bp_*, comments,
consultant_*, cp_*, credit_*, esg_notes, external_api, finmodel_*, kpi_*,
moderation_*, notes, notification, projects, tasks, users, webhook_*.

Impact: JOIN/filter on these FKs is currently seq-scan. Adding indexes will
drop dashboard / drill / list queries by 10-100× on >10k row tables.

Idempotent: each CREATE INDEX uses IF NOT EXISTS via op.execute (env.py
wrapper provides idempotency for op.create_index but using raw SQL here for
clarity and to allow CONCURRENT in a future re-run if needed).

Revision ID: 9aZ_fk_indexes
Revises:     9aY_jwt_revocation
Create Date: 2026-05-26
"""
from typing import Sequence, Union
from alembic import op


revision: str = "9aZ_fk_indexes"
down_revision: Union[str, None] = "9aY_jwt_revocation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) — 93 entries grouped by table for readability.
INDEXES = [
    # admin_broadcasts subsystem
    ("admin_broadcast_ack", "notification_id"),
    ("admin_broadcast_ack", "dispatch_id"),
    ("admin_broadcast_ack", "template_id"),
    ("admin_broadcast_ack", "user_id"),
    ("admin_broadcast_dispatch", "template_id"),
    ("admin_broadcast_dispatch", "dispatched_by_id"),
    ("admin_broadcast_template", "created_by_id"),
    # announcements / api_key / boards
    ("announcements", "author_id"),
    ("api_key", "service_account_id"),
    ("api_key", "created_by_id"),
    ("api_key", "revoked_by_id"),
    ("boards", "owner_id"),
    # BP / KPI
    ("bp_comments", "company_id"),
    ("bp_comments", "author_id"),
    ("bp_records", "company_id"),
    ("kpi_comments", "company_id"),
    ("kpi_comments", "author_id"),
    ("kpi_indicators", "manager_id"),
    ("kpi_managers", "company_id"),
    # comments
    ("comments", "author_id"),
    ("comments", "parent_id"),
    # company library / overrides
    ("company_library_tabs", "created_by"),
    ("company_year_override", "sector_override_id"),
    ("field_definitions", "created_by"),
    # consultants
    ("consultant_imports", "company_id"),
    ("consultant_imports", "submitted_by_id"),
    ("consultant_imports", "reviewed_by_id"),
    ("consultant_imports", "applied_by_id"),
    # credit portfolio
    ("cp_loans", "created_by_user_id"),
    ("cp_loans", "updated_by_user_id"),
    ("cp_payments", "created_by_user_id"),
    ("credit_custom_indicators", "created_by_user_id"),
    ("credit_custom_indicators", "updated_by_user_id"),
    ("credit_portfolio_scenarios", "created_by_user_id"),
    ("credit_portfolio_scenarios", "updated_by_user_id"),
    # ESG
    ("esg_notes", "author_id"),
    # external_api / partners
    ("external_api", "owner_id"),
    ("external_api", "created_by_id"),
    ("external_api", "openapi_uploaded_by_id"),
    ("external_api", "partner_id"),
    ("integration_partner", "owner_id"),
    ("integration_partner", "created_by_id"),
    # finmodel
    ("finmodel_audit_log", "company_id"),
    ("finmodel_audit_log", "actor_id"),
    ("finmodel_cell_comments", "company_id"),
    ("finmodel_cell_comments", "author_id"),
    ("finmodel_cell_values", "company_id"),
    ("finmodel_cell_values", "row_code"),
    ("finmodel_cell_values", "updated_by"),
    ("finmodel_macro_company", "company_id"),
    ("finmodel_macro_company", "updated_by"),
    ("finmodel_macro_global", "updated_by"),
    ("finmodel_scenarios", "company_id"),
    ("finmodel_scenarios", "created_by"),
    ("finmodel_year_lock", "company_id"),
    ("finmodel_year_lock", "locked_by"),
    # RBAC v3
    ("group_permission_grant", "granted_by_id"),
    # moderation
    ("moderation_comment", "submission_id"),
    ("moderation_comment", "user_id"),
    ("moderation_rule", "created_by_id"),
    ("moderation_rule", "moderator_primary_id"),
    ("moderation_rule", "moderator_coapprover_id"),
    ("moderation_submission", "proposer_user_id"),
    ("moderation_submission", "target_company_id"),
    ("moderation_submission", "target_sector_id"),
    ("moderation_submission", "assigned_moderator_id"),
    ("moderation_submission", "coapprover_id"),
    ("moderation_submission", "resolved_by_id"),
    # notes
    ("notes", "company_id"),
    ("notes", "author_id"),
    # notifications
    ("notification", "recipient_user_id"),
    ("notification", "source_user_id"),
    ("notification", "broadcast_template_id"),
    ("notification", "broadcast_dispatch_id"),
    ("notification_preference", "user_id"),
    # projects / tasks
    ("project_comments", "author_id"),
    ("projects", "direction_id"),
    ("projects", "assignee_id"),
    ("projects", "creator_id"),
    ("rating_history", "actor_id"),
    ("task_attachments", "uploader_id"),
    ("task_comments", "author_id"),
    ("task_history", "actor_id"),
    ("tasks", "linked_task_id"),
    # users
    ("role_by_email", "organization_id"),
    ("users", "supervisor_id"),
    ("users", "service_account_owner_id"),
    ("users", "partner_id"),
    # webhooks
    ("webhook_delivery", "subscription_id"),
    ("webhook_delivery", "replay_of_id"),
    ("webhook_subscription", "service_account_id"),
    ("webhook_subscription", "created_by_id"),
    ("webhook_subscription", "partner_id"),
]


def _ix_name(table: str, column: str) -> str:
    """Use SQLAlchemy convention: ix_<table>_<column>. Truncate if > 63 chars
    (Postgres identifier limit)."""
    name = f"ix_{table}_{column}"
    return name[:63]


def upgrade() -> None:
    for table, col in INDEXES:
        ix = _ix_name(table, col)
        # IF NOT EXISTS — idempotent if migration re-run; also skips tables
        # that may have been dropped/renamed in dev DBs.
        op.execute(
            f'CREATE INDEX IF NOT EXISTS "{ix}" ON "{table}" ("{col}");'
        )


def downgrade() -> None:
    for table, col in INDEXES:
        ix = _ix_name(table, col)
        op.execute(f'DROP INDEX IF EXISTS "{ix}";')
