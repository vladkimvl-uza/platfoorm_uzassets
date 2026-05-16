"""Pack 7.69 — drop old financial_models tables, create flat JSONB storage for monolith-lift FinModel.

Revision ID: 0027_finmodel_lift
Revises: 0026_financials_consolidated
Create Date: 2026-05-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0027_finmodel_lift"
down_revision: Union[str, None] = "0026_financials_consolidated"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the 5 old financial_models tables (from migration 0017) and create
    a single-row JSONB storage for the monolith-lifted Финансовая модель."""

    # 1. Drop old tables (no data lost since they were never populated successfully)
    # IF EXISTS guard — table names from migration 0017
    for tbl in (
        "financial_model_audit",
        "financial_model_imports",
        "financial_model_drivers",
        "financial_model_cells",
        "financial_models",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")

    # 2. Create new flat storage table. Single row holding the entire _db.finModel
    #    object as JSONB. Schema mirrors Firebase RTDB /finModel path structure.
    op.create_table(
        "finmodel_storage",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("data", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )

    # 3. Seed one empty row (id=1) so endpoints can always read/write
    op.execute("INSERT INTO finmodel_storage (id, data) VALUES (1, '{}'::jsonb) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.drop_table("finmodel_storage")
    # Note: old financial_models tables are NOT recreated on downgrade (irreversible cleanup)
