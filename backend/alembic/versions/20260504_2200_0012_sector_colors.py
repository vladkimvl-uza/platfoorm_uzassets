"""canonical sector colors from legacy

Revision ID: 0012_sector_colors
Revises: 0011_sectors_perms
Create Date: 2026-05-04 22:00:00.000000

Aligns sector color_hex values with the legacy's canonical SECTORS
constant (line ~6766 of index.html) so the Vue frontend's border-left
indicator strip matches the production UI exactly.

Source colors (verbatim from legacy):
  mining       → #9B8EC4   (lavender)
  oilgas       → #0A7B5E   (deep teal)
  energy       → #EF9F27   (amber)
  transport    → #378ADD   (azure blue)
  other        → #888780   (warm gray)
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0012_sector_colors"
down_revision: Union[str, None] = "0011_sectors_perms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SECTOR_COLOR_MAP = [
    ("mining_metallurgy",        "#9B8EC4"),
    ("oil_gas",                  "#0A7B5E"),
    ("energy",                   "#EF9F27"),
    ("transport_communications", "#378ADD"),
    ("other",                    "#888780"),
]


def upgrade() -> None:
    for code, color in SECTOR_COLOR_MAP:
        op.execute(
            f"UPDATE sectors SET color_hex = '{color}', updated_at = NOW() "
            f"WHERE code = '{code}';"
        )


def downgrade() -> None:
    op.execute("UPDATE sectors SET color_hex = NULL WHERE code IN "
               "('mining_metallurgy','oil_gas','energy','transport_communications','other');")
