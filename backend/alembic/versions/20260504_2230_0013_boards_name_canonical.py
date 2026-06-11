"""normalize boards.name to canonical company.name_short

Revision ID: 0013_boards_name_canonical
Revises: 0012_sector_colors
Create Date: 2026-05-04 22:30:00.000000

The Boards / Projects views display the board's company column. For boards
that are linked to a canonical company (company_id IS NOT NULL), the column
should display company.name_short — the short canonical name agreed with
the platform owner (e.g. "ТШТХ", "УТЙ", "Uzairways").

But the original BoardsMigrator imported boards.name verbatim from legacy store,
where the same boards often had long historical names like "Тошшахартрансхизмат"
or mixed-script titles like "Узбекистон темир йуллари". Result: Boards/Projects
list showed inconsistent company labels — some short canonical, some legacy long.

This migration sets boards.name = companies.name_short for every board where
companies.name_short is non-null and boards.company_id matches.

Boards with NULL company_id (free-form, not tied to an SOE) keep their original name.
The BoardsMigrator is also updated to do this on future imports — see migrators.py.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0013_boards_name_canonical"
down_revision: Union[str, None] = "0012_sector_colors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === Step 1: enforce canonical name_short for all 22 companies =========
    # Safety net for installs where migration 0010 partially failed or where
    # name_short was overwritten by post-import edits. The list below mirrors
    # 0010_canonical_names exactly. UPDATE-only — does not insert/delete.
    canonical_short = [
        ("ngmk", "НГМК"),
        ("nur",  "Навоийуран"),
        ("agmk", "АГМК"),
        ("umk",  "Узметкомбинат"),
        ("uug",  "Узбекуголь"),
        ("ung",  "Узбекнефтегаз"),
        ("utg",  "Узтрансгаз"),
        ("hgt",  "Худудгазтаъминот"),
        ("ugt",  "UzGasTrade"),
        ("nes",  "НЭС"),
        ("tes",  "ТЭС"),
        ("res",  "РЭС"),
        ("uge",  "Узгидроэнерго"),
        ("uty",  "УТЙ"),
        ("uhy",  "Uzairways"),
        ("uap",  "Uzairports"),
        ("tst",  "ТШТХ"),
        ("utc",  "Узбектелеком"),
        ("upt",  "Узпочта"),
        ("uks",  "Узкимёсаноат"),
        ("naz",  "Навоийазот"),
        ("uas",  "Узавтосаноат"),
    ]
    for code, name_short in canonical_short:
        op.execute(
            f"UPDATE companies SET name_short = '{name_short}', updated_at = NOW() "
            f"WHERE code = '{code}' AND (name_short IS NULL OR name_short <> '{name_short}');"
        )

    # === Step 2: snapshot board.name into extra.legacy_name then overwrite =
    # Snapshot the prior names into extra so we don't lose history.
    op.execute("""
        UPDATE boards b
        SET    extra = COALESCE(extra, '{}'::jsonb)
                       || jsonb_build_object('legacy_name', b.name)
        WHERE  b.company_id IS NOT NULL
          AND  EXISTS (
                 SELECT 1 FROM companies c
                 WHERE  c.id = b.company_id
                   AND  c.name_short IS NOT NULL
                   AND  c.name_short <> ''
                   AND  c.name_short <> b.name
               );
    """)

    # Then overwrite boards.name with the canonical short name.
    op.execute("""
        UPDATE boards b
        SET    name = c.name_short,
               updated_at = NOW()
        FROM   companies c
        WHERE  b.company_id = c.id
          AND  c.name_short IS NOT NULL
          AND  c.name_short <> ''
          AND  c.name_short <> b.name;
    """)


def downgrade() -> None:
    # Restore from extra.legacy_name if present
    op.execute("""
        UPDATE boards b
        SET    name = b.extra->>'legacy_name',
               updated_at = NOW()
        WHERE  b.extra ? 'legacy_name'
          AND  b.extra->>'legacy_name' IS NOT NULL
          AND  b.extra->>'legacy_name' <> '';
    """)
