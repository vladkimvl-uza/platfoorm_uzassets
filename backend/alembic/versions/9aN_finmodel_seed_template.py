"""Seed finmodel_template_rows from JSON fixture.

Loads `backend/app/seed/finmodel_template_rows.json` into the static
template-rows lookup. Skipping rows that already exist (idempotent).

Revision ID: 9aN_finmodel_seed_template
Revises:     9aM_finmodel_v2_init
"""
import json
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9aN_finmodel_seed_template"
down_revision: Union[str, None] = "9aM_finmodel_v2_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    seed_path = Path(__file__).parent.parent.parent / "app" / "seed" / "finmodel_template_rows.json"
    if not seed_path.exists():
        return  # nothing to seed
    payload = json.loads(seed_path.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])

    conn = op.get_bind()
    for r in rows:
        # tuple shape: [code, section, order_idx, parent_code, row_type,
        #               name_ru, name_uz, name_uz_cyr, name_en,
        #               formula, sign_convention, is_indent, legacy_note]
        if len(r) < 13:
            continue
        (code, section, order_idx, parent_code, row_type,
         name_ru, name_uz, name_uz_cyr, name_en,
         formula, sign_convention, is_indent, legacy_note) = r
        conn.execute(
            sa.text("""
                INSERT INTO finmodel_template_rows
                  (code, section, order_idx, parent_code, row_type,
                   name_ru, name_uz, name_uz_cyr, name_en,
                   formula, ifrs_category, sign_convention, is_indent, legacy_note)
                VALUES
                  (:code, :section, :order_idx, :parent_code, :row_type,
                   :name_ru, :name_uz, :name_uz_cyr, :name_en,
                   :formula, NULL, :sign_convention, :is_indent, :legacy_note)
                ON CONFLICT (code) DO NOTHING
            """),
            {
                "code": code, "section": section, "order_idx": order_idx,
                "parent_code": parent_code, "row_type": row_type,
                "name_ru": name_ru, "name_uz": name_uz, "name_uz_cyr": name_uz_cyr, "name_en": name_en,
                "formula": formula, "sign_convention": sign_convention,
                "is_indent": is_indent or 0, "legacy_note": legacy_note,
            },
        )


def downgrade() -> None:
    op.execute("TRUNCATE finmodel_template_rows CASCADE")
