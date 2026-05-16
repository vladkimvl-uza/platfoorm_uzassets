"""seed 21 baseline canonical portfolio companies

Revision ID: 0003_companies
Revises: 0002_permissions
Create Date: 2026-05-04 14:00:00.000000

These are the 21 canonical state-owned enterprises the platform tracks.
The list is taken verbatim from the legacy monolith (`var COMPANIES = [...]`,
lines ~6774-6794 of index.html) where the codes were authoritative.

The Firebase migrator may have already auto-created some of these companies
when financial data referenced their codes — so we use ON CONFLICT (code)
DO NOTHING to preserve any existing records and just fill in the missing ones.

After this migration runs:
  - Companies with /financials data in Firebase: keep auto-created entries
  - Companies in /pf/customCompanies: keep entries with is_custom=TRUE
  - Companies missing from Firebase entirely: get inserted here as canonical stubs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_companies"
down_revision: Union[str, None] = "0002_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (code_lower, name_short, name_ru, sector_code, sort_order)
# Order roughly matches the monolith's array.
COMPANIES = [
    # --- Mining ---
    ("ngmk",  "НГМК",         "АО «Навоийский ГМК»",                "mining",     10),
    ("nur",   "Навоийуран",   "Навоийуран",                          "mining",     20),
    ("agmk",  "АГМК",         "АО «Алмалыкский ГМК»",                "mining",     30),
    ("umk",   "Узметкомбинат","АО «Узметкомбинат»",                  "metallurgy", 40),
    ("uug",   "Узбекуголь",   "АО «Узбекуголь»",                     "mining",     50),

    # --- Oil & gas ---
    ("ung",   "Узбекнефтегаз","АО «Узбекнефтегаз»",                  "oil_gas",    60),
    ("utg",   "Узтрансгаз",   "АО «Узтрансгаз»",                     "oil_gas",    70),
    ("ugt",   "UzGasTrade",   "UzGasTrade",                          "oil_gas",    80),
    ("hgt",   "Худудгазтаъминот", "АО «Худудгазтаъминот»",           "oil_gas",    90),

    # --- Energy ---
    ("nes",   "НЭС",          "АО «НЭС Узбекистана»",                "energy",    100),
    ("tes",   "ТЭС",          "АО «ТЭС Узбекистана»",                "energy",    110),
    ("res",   "РЭС",          "АО «РЭС»",                            "energy",    120),
    ("uge",   "Узгидроэнерго","АО «Узбекгидроэнерго»",               "energy",    130),

    # --- Transport ---
    ("uhy",   "Uzairways",    "Uzbekistan Airways",                   "transport", 140),
    ("uap",   "Uzairports",   "Uzbekistan Airports",                  "transport", 150),
    ("tst",   "ТШТХ",         "Тошшахартрансхизмат",                 "transport", 160),
    ("utc",   "UzTelecom",    "АО «UzTelecom»",                      "telecom",   170),
    ("upt",   "Узпочта",      "АО «Узбекистон Почтаси»",             "transport", 180),

    # --- Other (chemistry / auto) ---
    ("uks",   "Узкимёсаноат", "АО «Узкимёсаноат»",                   "chemistry", 190),
    ("naz",   "Навоийазот",   "АО «Навоийазот»",                     "chemistry", 200),
    ("uas",   "Узавтосаноат", "АО «УзАвто Саноат»",                  "other",     210),
]


def upgrade() -> None:
    bind = op.get_bind()

    # Build sector_code → id map from the already-seeded sectors table (migration 0001)
    sector_rows = bind.execute(sa.text("SELECT id, code FROM sectors")).fetchall()
    sector_by_code = {r.code: r.id for r in sector_rows}

    # Insert each canonical company. ON CONFLICT (code) DO NOTHING means:
    #   - If the Firebase migrator already auto-created this company, keep it untouched
    #   - If it doesn't exist yet, insert canonical stub
    insert_sql = sa.text("""
        INSERT INTO companies (
            id, code, name_ru, name_short, sector_id,
            is_active, is_custom, sort_order, created_at, updated_at
        )
        VALUES (
            gen_random_uuid(), :code, :name_ru, :name_short, :sector_id,
            TRUE, FALSE, :sort_order, NOW(), NOW()
        )
        ON CONFLICT (code) DO NOTHING
    """)

    # Also update existing canonical companies that have NULL sector_id
    # (e.g. auto-created by the Firebase migrator before this migration ran)
    update_sector_sql = sa.text("""
        UPDATE companies
        SET sector_id  = COALESCE(sector_id, :sector_id),
            sort_order = CASE WHEN sort_order = 0 THEN :sort_order ELSE sort_order END,
            updated_at = NOW()
        WHERE code = :code
    """)

    for code, name_short, name_ru, sector_code, sort_order in COMPANIES:
        sector_id = sector_by_code.get(sector_code)
        bind.execute(insert_sql, {
            "code":       code,
            "name_ru":    name_ru,
            "name_short": name_short,
            "sector_id":  sector_id,
            "sort_order": sort_order,
        })
        # Backfill sector_id and sort_order for already-existing rows
        if sector_id is not None:
            bind.execute(update_sector_sql, {
                "code":       code,
                "sector_id":  sector_id,
                "sort_order": sort_order,
            })

    # Fix-up: 3 canonical companies (UPT, UKS, UGE) that may have been incorrectly
    # marked is_custom=TRUE because they were placed in /pf/customCompanies in the
    # legacy Firebase. Reclassify them as canonical (is_custom=FALSE).
    # Also update their sector_id if they currently have NULL.
    fix_sql = sa.text("""
        UPDATE companies
        SET is_custom = FALSE,
            sector_id = COALESCE(sector_id, :sector_id),
            sort_order = :sort_order,
            updated_at = NOW()
        WHERE code = :code AND is_custom = TRUE
    """)
    canonical_overrides = {
        "upt": ("transport", 180),
        "uks": ("chemistry", 190),
        "uge": ("energy",    130),
    }
    for code, (sector_code, sort_order) in canonical_overrides.items():
        bind.execute(fix_sql, {
            "code": code,
            "sector_id": sector_by_code.get(sector_code),
            "sort_order": sort_order,
        })


def downgrade() -> None:
    bind = op.get_bind()
    codes = [c[0] for c in COMPANIES]
    # Only delete companies that have NO data linked to them
    # (financials, ratings, etc.) — to avoid breaking FK refs.
    bind.execute(
        sa.text("""
            DELETE FROM companies
            WHERE code = ANY(:codes)
              AND is_custom = FALSE
              AND NOT EXISTS (SELECT 1 FROM financial_reports WHERE company_id = companies.id)
        """),
        {"codes": codes},
    )
