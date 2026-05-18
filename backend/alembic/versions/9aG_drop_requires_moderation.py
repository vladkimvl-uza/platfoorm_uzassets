"""Drop unused users.requires_moderation column (Pack 148-followup).

Revision ID: 9aG_drop_requires_moderation
Revises: 9aF_moderation_apply_tracking
Create Date: 2026-05-16

`requires_moderation` was seeded as a per-user flag but no gate logic ever
read it (audit found it referenced only in the listing endpoint + UI
toggle). Removed in favor of `is_external` (the actual driver of rule
matching via `trigger_is_external`).

To replicate the old "internal user that needs moderation" intent, set
`is_external=True` on them — rule matching treats them identically.
"""
from alembic import op
import sqlalchemy as sa


revision = "9aG_drop_requires_moderation"
down_revision = "9aF_moderation_apply_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "requires_moderation")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "requires_moderation",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
