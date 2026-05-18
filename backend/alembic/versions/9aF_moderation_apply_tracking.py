"""Add apply-dispatcher tracking columns to moderation_submission (Pack 148-followup B1).

Revision ID: 9aF_moderation_apply_tracking
Revises: 9aE_ebitda_anchor_flag
Create Date: 2026-05-16

When `approve()` succeeds, the apply-dispatcher routes the approved change
to a module-specific handler that performs the actual write. Outcome is
persisted here so the UI can show "applied / failed / skipped (no handler)"
and admins can retry failed applies.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9aF_moderation_apply_tracking"
down_revision = "9aE_ebitda_anchor_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "moderation_submission",
        sa.Column("apply_status", sa.String(16), nullable=True),
    )
    op.add_column(
        "moderation_submission",
        sa.Column("apply_error", sa.String(500), nullable=True),
    )
    op.add_column(
        "moderation_submission",
        sa.Column("apply_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("moderation_submission", "apply_result")
    op.drop_column("moderation_submission", "apply_error")
    op.drop_column("moderation_submission", "apply_status")
