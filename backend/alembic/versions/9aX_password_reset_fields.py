"""password_reset_* fields on users (Pack 152 — forgot-password via Telegram)

4 nullable fields added so user-initiated password reset doesn't need a new table:
  - password_reset_token_hashed (sha256 of reset_id returned to client)
  - password_reset_code_hashed  (bcrypt of 6-digit code delivered to Telegram)
  - password_reset_expires_at   (TTL, default 5 min from issue)
  - password_reset_attempts     (failed-code counter, locked at 5)

Idempotent ops (env.py wrapper) — safe on re-run.

Revision ID: 9aX_password_reset_fields
Revises:     9aW_attachment_access_denial
Create Date: 2026-05-22 12:30:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "9aX_password_reset_fields"
down_revision: Union[str, None] = "9aW_attachment_access_denial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_reset_token_hashed", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("password_reset_code_hashed",  sa.String(64), nullable=True))
    op.add_column("users", sa.Column("password_reset_expires_at",   sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("password_reset_attempts",     sa.Integer, nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("users", "password_reset_attempts")
    op.drop_column("users", "password_reset_expires_at")
    op.drop_column("users", "password_reset_code_hashed")
    op.drop_column("users", "password_reset_token_hashed")
