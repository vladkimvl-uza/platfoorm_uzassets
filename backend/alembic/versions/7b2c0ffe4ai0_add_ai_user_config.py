"""add ai_user_config

Revision ID: 7b2c0ffe4ai0
Revises: 7a1c0ffe4ai0
Create Date: 2026-05-09 12:00:00
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7b2c0ffe4ai0"
down_revision = "7a1c0ffe4ai0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_user_config",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(length=32), server_default="universal", nullable=False),
        sa.Column("style", sa.String(length=32), server_default="structured", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.25", nullable=False),
        sa.Column("max_tokens", sa.Integer(), server_default="16000", nullable=False),
        sa.Column("custom_instructions", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_user_config")
