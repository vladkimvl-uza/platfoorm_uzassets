"""Add explicit Uzbek Cyrillic names to companies and sectors.

Revision ID: 9b5_company_sector_uz_cyr
Revises: 9b4_rbac_screen_permissions
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b5_company_sector_uz_cyr"
down_revision: Union[str, None] = "9b4_rbac_screen_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("name_uz_cyr", sa.String(255), nullable=True))
    op.add_column("sectors", sa.Column("name_uz_cyr", sa.String(255), nullable=True))

    # The legacy name_uz column contains Cyrillic for the canonical catalog.
    # Preserve it in the explicit field; Latin-only rows stay untouched.
    for table in ("companies", "sectors"):
        op.execute(
            f"""
            UPDATE {table}
               SET name_uz_cyr = name_uz
             WHERE name_uz_cyr IS NULL
               AND name_uz ~ '[А-Яа-яЁёЎўҒғҚқҲҳ]'
            """
        )


def downgrade() -> None:
    op.drop_column("sectors", "name_uz_cyr")
    op.drop_column("companies", "name_uz_cyr")
