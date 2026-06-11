"""sweep-link orphan boards/tasks/projects to canonical companies

Revision ID: 0014_company_link_sweep
Revises: 0013_boards_name_canonical
Create Date: 2026-05-04 22:50:00.000000

After migration 0013 some boards still had `company_id IS NULL` because the
BoardsMigrator's lookup matched only against (code, name_ru, name_short).
legacy store often stores the legacy's COMPANIES[*].name field, which uses
historical variants like:

    "УзАвто Саноат"       → canonical Узавтосаноат (uas)
    "Uzbekistan Airways"  → canonical Uzairways    (uhy)
    "Uzbekistan Airports" → canonical Uzairports   (uap)
    "UzTelecom"           → canonical Узбектелеком (utc)
    "Узбекистон Почтаси"  → canonical Узпочта      (upt)
    "Узбекистон темир йуллари" → canonical УТЙ     (uty)

This migration fixes existing rows in three tables (boards, tasks, projects)
by:
    1. Stripping every char that's not a letter or digit, then lowercase
    2. Trying that key against a name-alias table built from the legacy
       AND a fuzzy normalised set of all canonical name fields

After linking, for any board that gained a company_id, we also overwrite
boards.name with companies.name_short — finishing what 0013 started.

Idempotent. Safe to re-run.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0014_company_link_sweep"
down_revision: Union[str, None] = "0013_boards_name_canonical"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Each row: (canonical company.code, alias_normalised_form)
# alias forms are pre-normalised (only [a-z0-9а-я], lowercase) to make matching
# robust to spacing, punctuation, case, and the use of legacy's vs canonical
# name forms. Add to this list as more orphans appear.
ALIASES = [
    # mining/metals
    ("ngmk", "ngmk"),
    ("ngmk", "навоийскийгмк"),
    ("ngmk", "нгмк"),
    ("nur",  "nur"),
    ("nur",  "навоийуран"),
    ("agmk", "agmk"),
    ("agmk", "алмалыкскийгмк"),
    ("agmk", "агмк"),
    ("umk",  "umk"),
    ("umk",  "узметкомбинат"),
    ("uug",  "uug"),
    ("uug",  "узбекуголь"),
    # oil & gas
    ("ung",  "ung"),
    ("ung",  "узбекнефтегаз"),
    ("utg",  "utg"),
    ("utg",  "узтрансгаз"),
    ("hgt",  "hgt"),
    ("hgt",  "худудгазтаъминот"),
    ("hgt",  "хгт"),
    ("ugt",  "ugt"),
    ("ugt",  "uzgastrade"),
    # energy
    ("nes",  "nes"),
    ("nes",  "нэс"),
    ("nes",  "национальныеэлектрическиесетиузбекистана"),
    ("tes",  "tes"),
    ("tes",  "тэс"),
    ("tes",  "тепловыеэлектрическиестанции"),
    ("res",  "res"),
    ("res",  "рэс"),
    ("res",  "региональныеэлектрическиесети"),
    ("uge",  "uge"),
    ("uge",  "узгидроэнерго"),
    ("uge",  "узбекгидроэнерго"),
    # transport / comms
    ("uty",  "uty"),
    ("uty",  "утй"),
    ("uty",  "узбекистонтемирйуллари"),       # Uzb Cyrillic
    ("uty",  "узбeкистонтeмирйуллари"),        # with Latin 'e' (in our seed)
    ("uty",  "uzbekistanrailways"),
    ("uhy",  "uhy"),
    ("uhy",  "uzairways"),
    ("uhy",  "uzbekistanairways"),
    ("uap",  "uap"),
    ("uap",  "uzairports"),
    ("uap",  "uzbekistanairports"),
    ("tst",  "tst"),
    ("tst",  "тштх"),
    ("tst",  "тошшахартрансхизмат"),
    ("utc",  "utc"),
    ("utc",  "uztelecom"),
    ("utc",  "узбектелеком"),
    ("upt",  "upt"),
    ("upt",  "узпочта"),
    ("upt",  "узбекистонпочтаси"),
    ("upt",  "uzpost"),
    # other
    ("uks",  "uks"),
    ("uks",  "узкимёсаноат"),
    ("uks",  "узкимесаноат"),
    ("naz",  "naz"),
    ("naz",  "навоийазот"),
    ("uas",  "uas"),
    ("uas",  "узавтосаноат"),
    ("uas",  "узавтосаноат"),
    ("uas",  "узавтосаноатао"),
]


def upgrade() -> None:
    # ── Build temp alias table ────────────────────────────────────────────
    op.execute("""
        CREATE TEMP TABLE _company_aliases (
            company_code  TEXT NOT NULL,
            alias_norm    TEXT NOT NULL PRIMARY KEY
        );
    """)
    for code, alias in ALIASES:
        op.execute(
            f"INSERT INTO _company_aliases (company_code, alias_norm) "
            f"VALUES ('{code}', '{alias}') ON CONFLICT DO NOTHING;"
        )

    # Plus auto-insert: for every canonical company, normalise each of its
    # five name fields and add as alias. This catches anything the explicit
    # list above missed.
    op.execute("""
        INSERT INTO _company_aliases (company_code, alias_norm)
        SELECT c.code, regexp_replace(lower(coalesce(v, '')), '[^a-zа-я0-9ё]', '', 'g')
        FROM   companies c
        CROSS  JOIN LATERAL (VALUES (c.code), (c.name_short), (c.name_ru), (c.name_uz), (c.name_en)) AS x(v)
        WHERE  v IS NOT NULL AND v <> ''
          AND  regexp_replace(lower(v), '[^a-zа-я0-9ё]', '', 'g') <> ''
        ON CONFLICT DO NOTHING;
    """)

    # ── Sweep boards ──────────────────────────────────────────────────────
    op.execute("""
        UPDATE boards b
        SET    company_id = c.id,
               updated_at = NOW()
        FROM   _company_aliases a
        JOIN   companies c ON c.code = a.company_code
        WHERE  b.company_id IS NULL
          AND  a.alias_norm = regexp_replace(lower(coalesce(b.name, '')), '[^a-zа-я0-9ё]', '', 'g')
          AND  a.alias_norm <> '';
    """)

    # Same trick: tasks linked to boards but without company_id
    op.execute("""
        UPDATE tasks t
        SET    company_id = b.company_id,
               updated_at = NOW()
        FROM   boards b
        WHERE  t.company_id IS NULL
          AND  t.board_id   = b.id
          AND  b.company_id IS NOT NULL;
    """)

    # Projects: same backfill from boards
    op.execute("""
        UPDATE projects p
        SET    company_id = b.company_id,
               updated_at = NOW()
        FROM   boards b
        WHERE  p.company_id IS NULL
          AND  p.board_id   = b.id
          AND  b.company_id IS NOT NULL;
    """)

    # ── Refresh boards.name to canonical short for newly-linked rows ──────
    # Snapshot legacy then overwrite (same pattern as 0013).
    op.execute("""
        UPDATE boards b
        SET    extra = COALESCE(b.extra, '{}'::jsonb)
                       || jsonb_build_object('legacy_name', b.name)
        FROM   companies c
        WHERE  b.company_id = c.id
          AND  c.name_short IS NOT NULL
          AND  c.name_short <> ''
          AND  c.name_short <> b.name
          AND  NOT (b.extra ? 'legacy_name');
    """)
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
    # Restoring company_id NULLs would be data-destructive; skip.
    # Restoring board names from extra.legacy_name:
    op.execute("""
        UPDATE boards b
        SET    name = b.extra->>'legacy_name',
               updated_at = NOW()
        WHERE  b.extra ? 'legacy_name'
          AND  b.extra->>'legacy_name' IS NOT NULL
          AND  b.extra->>'legacy_name' <> '';
    """)
