"""users.tokens_invalid_before — JWT revocation cutoff (Pack-audit 2026-05-26).

After this column is set on a user, any access token with iat < tokens_invalid_before
is rejected by get_current_user(). Bumped on:
  • /auth/logout
  • /auth/change-password
  • /admin/mfa/{user_id}/disable (force-disable)
  • role / permission change
  • user deactivation
  • admin password reset

Idempotent op (env.py wrapper) — safe on re-run.

Revision ID: 9aY_jwt_revocation
Revises:     9aX_password_reset_fields
Create Date: 2026-05-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "9aY_jwt_revocation"
down_revision: Union[str, None] = "9aX_password_reset_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("tokens_invalid_before", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "tokens_invalid_before")
