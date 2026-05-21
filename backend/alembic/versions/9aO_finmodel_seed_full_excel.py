"""Full re-seed of finmodel_template_rows from real NSBU Excel example.

Replaces the partial 64-row seed (9aN) with the complete 87 BS + 27 PL rows
extracted from `Financial model - example.xlsx`, including:
  - column-A RU dashboard category (stored in `ifrs_category` column —
    reused for analytical dashboard grouping until proper IFRS mapping)
  - sub-aggregate rows (491, 601, 602) that the partial seed missed
  - corrected name_uz_cyr (proper Uzbek-cyrillic from Excel)

Strategy: UPSERT (ON CONFLICT DO UPDATE) — safe even if cell_values reference
rows. No truncation.

Revision ID: 9aO_finmodel_seed_full_excel
Revises:     9aN_finmodel_seed_template
"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aO_finmodel_seed_full_excel"
down_revision: Union[str, None] = "9aN_finmodel_seed_template"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    seed_path = Path(__file__).parent.parent.parent / "app" / "seed" / "finmodel_template_rows_v3.json"
    if not seed_path.exists():
        return
    rows = json.loads(seed_path.read_text(encoding="utf-8"))
    conn = op.get_bind()
    for r in rows:
        # `dashboard_category` from JSON → `ifrs_category` column
        conn.execute(
            sa.text("""
                INSERT INTO finmodel_template_rows
                  (code, section, order_idx, parent_code, row_type,
                   name_ru, name_uz, name_uz_cyr, name_en,
                   formula, ifrs_category, sign_convention, is_indent, legacy_note)
                VALUES
                  (:code, :section, :order_idx, :parent_code, :row_type,
                   :name_ru, :name_uz, :name_uz_cyr, :name_en,
                   :formula, :ifrs_category, :sign_convention, :is_indent, :legacy_note)
                ON CONFLICT (code) DO UPDATE SET
                  section         = EXCLUDED.section,
                  order_idx       = EXCLUDED.order_idx,
                  parent_code     = EXCLUDED.parent_code,
                  row_type        = EXCLUDED.row_type,
                  name_ru         = EXCLUDED.name_ru,
                  name_uz         = EXCLUDED.name_uz,
                  name_uz_cyr     = EXCLUDED.name_uz_cyr,
                  name_en         = EXCLUDED.name_en,
                  formula         = EXCLUDED.formula,
                  ifrs_category   = EXCLUDED.ifrs_category,
                  sign_convention = EXCLUDED.sign_convention,
                  is_indent       = EXCLUDED.is_indent,
                  legacy_note     = EXCLUDED.legacy_note
            """),
            {
                "code":            r["code"],
                "section":         r["section"],
                "order_idx":       r["order_idx"],
                "parent_code":     r.get("parent_code"),
                "row_type":        r["row_type"],
                "name_ru":         r["name_ru"],
                "name_uz":         r.get("name_uz"),
                "name_uz_cyr":     r.get("name_uz_cyr"),
                "name_en":         r.get("name_en"),
                "formula":         r.get("formula"),
                "ifrs_category":   r.get("dashboard_category"),
                "sign_convention": r.get("sign_convention"),
                "is_indent":       r.get("is_indent") or 0,
                "legacy_note":     r.get("legacy_note"),
            },
        )


def downgrade() -> None:
    # Cannot revert to partial seed safely; no-op
    pass
