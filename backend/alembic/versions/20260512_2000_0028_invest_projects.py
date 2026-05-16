"""Pack 8.0 — Invest Projects storage (single-row JSONB), mirrors finmodel_storage pattern.

Revision ID: 0028_invest_projects
Revises: 0027_finmodel_lift
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0028_invest_projects"
down_revision: Union[str, None] = "0027_finmodel_lift"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "invest_projects_storage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )
    op.execute("INSERT INTO invest_projects_storage (id, data) VALUES (1, '{}'::jsonb) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.drop_table("invest_projects_storage")
