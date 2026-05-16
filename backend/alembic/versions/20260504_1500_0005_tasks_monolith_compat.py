"""add monolith-compat fields to tasks and boards

Revision ID: 0005_tasks_monolith_compat
Revises: 0004_monolith_seeds
Create Date: 2026-05-04 15:00:00.000000

The existing Task/Board schema (from migration 0001) is normalized for the
new platform but missing some fields that the legacy monolith uses heavily:

  Task:
    num                — manual hierarchical numbering string ("1.2.3")
    board_id           — direct FK to boards (monolith uses board_id directly,
                          not via BoardColumn/BoardCard)
    portfolio_year     — year tag for filtering (KPI portfolio year)
    is_project         — project-vs-task distinction (parent/child)
    assignee_email     — denormalized email (legacy assignees may not have User rows)
    assignee_name      — denormalized name string
    linked_task_id     — soft link between related tasks

  Board:
    color_hex          — board accent color (already in extra, but promote to column)
    sector_code        — board's sector tag (for filtering by sector)

These fields enable a clean migration of /pf/tasks and /pf/boards from
Firebase, preserving all numbering, project hierarchy, and ProjectsFlow
semantics from the monolith.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_tasks_monolith_compat"
down_revision: Union[str, None] = "0004_monolith_seeds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Task additions ---
    op.add_column("tasks", sa.Column("num", sa.String(64), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "board_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("boards.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("tasks", sa.Column("portfolio_year", sa.Integer(), nullable=True))
    op.add_column("tasks", sa.Column("is_project", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tasks", sa.Column("assignee_email", sa.String(255), nullable=True))
    op.add_column("tasks", sa.Column("assignee_name", sa.String(255), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "linked_task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Indexes for common queries
    op.create_index("ix_tasks_board_status", "tasks", ["board_id", "status"])
    op.create_index("ix_tasks_portfolio_year", "tasks", ["portfolio_year"])
    op.create_index("ix_tasks_assignee_email", "tasks", ["assignee_email"])

    # --- Board additions ---
    op.add_column("boards", sa.Column("color_hex", sa.String(9), nullable=True))
    op.add_column("boards", sa.Column("sector_code", sa.String(32), nullable=True))
    op.create_index("ix_boards_sector_code", "boards", ["sector_code"])


def downgrade() -> None:
    op.drop_index("ix_boards_sector_code", table_name="boards")
    op.drop_column("boards", "sector_code")
    op.drop_column("boards", "color_hex")

    op.drop_index("ix_tasks_assignee_email", table_name="tasks")
    op.drop_index("ix_tasks_portfolio_year", table_name="tasks")
    op.drop_index("ix_tasks_board_status", table_name="tasks")
    op.drop_column("tasks", "linked_task_id")
    op.drop_column("tasks", "assignee_name")
    op.drop_column("tasks", "assignee_email")
    op.drop_column("tasks", "is_project")
    op.drop_column("tasks", "portfolio_year")
    op.drop_column("tasks", "board_id")
    op.drop_column("tasks", "num")
