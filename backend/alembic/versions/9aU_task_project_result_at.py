"""binary "результат" for tasks + projects

Adds `result_at` (timestamp, nullable) to both tables. Semantic:
  - NULL          → no result yet (work not accepted)
  - <timestamp>   → result accepted at that moment

Replaces the legacy's 4-state resultStatus (review/agreement/accepted/
rejected) with a binary present/absent — simpler model agreed with the
business owner.

UI alert: any row with status='done' AND result_at IS NULL gets a red
"Нужен результат" badge. Coverage metric: count(result_at) / count(done).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aU_task_project_result_at"
down_revision: Union[str, None] = "9aT_audit_chain_lock_sentinel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("result_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("result_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index — only rows where the result is set. Used by coverage
    # queries and the "missing result" alert.
    op.create_index(
        "ix_tasks_result_at",
        "tasks",
        ["result_at"],
        postgresql_where=sa.text("result_at IS NOT NULL"),
    )
    op.create_index(
        "ix_projects_result_at",
        "projects",
        ["result_at"],
        postgresql_where=sa.text("result_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_projects_result_at", table_name="projects")
    op.drop_index("ix_tasks_result_at", table_name="tasks")
    op.drop_column("projects", "result_at")
    op.drop_column("tasks", "result_at")
