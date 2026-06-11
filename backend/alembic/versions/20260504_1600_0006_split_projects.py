"""split projects from tasks into a separate `projects` table

Revision ID: 0006_split_projects
Revises: 0005_tasks_legacy_compat
Create Date: 2026-05-04 16:00:00.000000

The legacy legacy stored projects and tasks in one legacy store array
(`/pf/tasks`) distinguished only by `_isProject` flag. The new platform
separates them into two physical tables for cleaner queries and clearer
domain model.

After this migration:
  - `projects` is a new table with the same shape as `tasks` minus
    `is_project` (the discriminator, no longer needed) and
    `linked_task_id` (replaced by `parent_project_id` semantics).
  - `tasks.is_project` column is dropped.
  - `tasks.project_id` FK is added so a task can reference its parent project.

Existing rows in `tasks` with `is_project=TRUE` are moved to `projects`.
The legacy_id is preserved on both sides so cross-references resolve.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_split_projects"
down_revision: Union[str, None] = "0005_tasks_legacy_compat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =====================================================================
    # 1. CREATE TABLE projects (mirrors tasks fields except discriminator)
    # =====================================================================
    op.create_table(
        "projects",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        # Core
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("num", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), server_default="new", nullable=False),
        sa.Column("priority", sa.String(16), server_default="medium", nullable=False),

        # Refs
        sa.Column("board_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("boards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("direction_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("directions.id", ondelete="SET NULL"), nullable=True),

        # Ownership
        sa.Column("assignee_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assignee_email", sa.String(255), nullable=True),
        sa.Column("assignee_name",  sa.String(255), nullable=True),
        sa.Column("creator_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Dates
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("due_date",   sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),

        # Metadata
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("portfolio_year",   sa.Integer(), nullable=True),
        sa.Column("tags",  sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("extra", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False),

        # Legacy carry
        sa.Column("legacy_id", sa.String(64), nullable=True, unique=True),
    )
    op.create_index("ix_projects_status",         "projects", ["status"])
    op.create_index("ix_projects_priority",       "projects", ["priority"])
    op.create_index("ix_projects_board_id",       "projects", ["board_id"])
    op.create_index("ix_projects_company_id",     "projects", ["company_id"])
    op.create_index("ix_projects_assignee_email", "projects", ["assignee_email"])
    op.create_index("ix_projects_portfolio_year", "projects", ["portfolio_year"])
    op.create_index("ix_projects_due_date",       "projects", ["due_date"])
    op.create_index("ix_projects_legacy_id",      "projects", ["legacy_id"])

    # =====================================================================
    # 2. Add tasks.project_id FK (so tasks can reference their parent project)
    # =====================================================================
    op.add_column(
        "tasks",
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])

    # =====================================================================
    # 3. Move existing is_project=TRUE rows from tasks → projects
    #    (idempotent: if no such rows, this is a no-op)
    # =====================================================================
    op.execute("""
        INSERT INTO projects (
            id, created_at, updated_at,
            title, description, num, status, priority,
            board_id, company_id, direction_id,
            assignee_id, assignee_email, assignee_name, creator_id,
            start_date, due_date, completed_at,
            progress_percent, portfolio_year,
            tags, extra, is_archived, legacy_id
        )
        SELECT
            id, created_at, updated_at,
            title, description, num, status, priority,
            board_id, company_id, direction_id,
            assignee_id, assignee_email, assignee_name, creator_id,
            start_date, due_date, completed_at,
            progress_percent, portfolio_year,
            tags, extra, is_archived, legacy_id
        FROM tasks
        WHERE is_project = TRUE
    """)
    op.execute("DELETE FROM tasks WHERE is_project = TRUE")

    # =====================================================================
    # 4. Drop the discriminator column from tasks (no longer needed)
    # =====================================================================
    op.drop_column("tasks", "is_project")


def downgrade() -> None:
    # Add discriminator back
    op.add_column("tasks", sa.Column(
        "is_project", sa.Boolean(), server_default=sa.false(), nullable=False,
    ))

    # Move project rows back into tasks (best-effort — we lose project_id refs)
    op.execute("""
        INSERT INTO tasks (
            id, created_at, updated_at,
            title, description, num, status, priority,
            board_id, company_id, direction_id,
            assignee_id, assignee_email, assignee_name, creator_id,
            start_date, due_date, completed_at,
            progress_percent, portfolio_year,
            tags, extra, is_archived, legacy_id, is_project
        )
        SELECT
            id, created_at, updated_at,
            title, description, num, status, priority,
            board_id, company_id, direction_id,
            assignee_id, assignee_email, assignee_name, creator_id,
            start_date, due_date, completed_at,
            progress_percent, portfolio_year,
            tags, extra, is_archived, legacy_id, TRUE
        FROM projects
    """)
    op.execute("DELETE FROM projects")

    op.drop_index("ix_tasks_project_id", table_name="tasks")
    op.drop_column("tasks", "project_id")

    op.drop_index("ix_projects_legacy_id",      table_name="projects")
    op.drop_index("ix_projects_due_date",       table_name="projects")
    op.drop_index("ix_projects_portfolio_year", table_name="projects")
    op.drop_index("ix_projects_assignee_email", table_name="projects")
    op.drop_index("ix_projects_company_id",     table_name="projects")
    op.drop_index("ix_projects_board_id",       table_name="projects")
    op.drop_index("ix_projects_priority",       table_name="projects")
    op.drop_index("ix_projects_status",         table_name="projects")
    op.drop_table("projects")
