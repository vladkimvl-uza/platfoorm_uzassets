"""0023 consultants tables

Creates:
  consultants                 — master list (id, code, name_ru, color, abbr,
                                is_big4, is_active, sort_order, extra)
  consultant_assignments      — M:N task ↔ consultant (task_id, consultant_id)

Schema mirrors monolith CONSULTANTS array (17 firms incl. Big4) + task.consultant
field which can be a string or array. The `consultant_assignments` table
flattens the array shape: one row per (task_id, consultant_id) pair.

Revision ID: 0023_consultants
Revises:    0022_procurement_closures
Create Date: 2026-05-06 11:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0023_consultants"
down_revision = "0022_procurement_closures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── consultants master list ─────────────────────────────────────
    op.create_table(
        "consultants",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"),
                  nullable=False, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name_ru", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=True),
        sa.Column("abbr", sa.String(32), nullable=True),
        sa.Column("color_hex", sa.String(9), nullable=True),
        sa.Column("is_big4", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_consultants_is_big4", "consultants", ["is_big4"])
    op.create_index("ix_consultants_is_active", "consultants", ["is_active"])

    # ─── consultant_assignments (M:N task ↔ consultant) ──────────────
    op.create_table(
        "consultant_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"),
                  nullable=False, primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tasks.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("consultant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("consultants.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="task"),
        # 'task' = derived from task.consultant field
        # 'lookup' = added via CONSULTANT_LOOKUP (board::num key)
        # 'manual' = added by user via Vue UI
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("task_id", "consultant_id",
                            name="uq_consultant_assignment_pair"),
    )


def downgrade() -> None:
    op.drop_table("consultant_assignments")
    op.drop_index("ix_consultants_is_active", table_name="consultants")
    op.drop_index("ix_consultants_is_big4", table_name="consultants")
    op.drop_table("consultants")
