"""canonical company + sector names (22 companies, 5 sectors)

Revision ID: 0010_canonical_names
Revises: 0009_admin_users_perm
Create Date: 2026-05-04 20:00:00.000000

Replaces the seeded company data with the canonical list provided
by the platform owner. Adds the 22nd company (UTY — Uzbekistan Railways)
and consolidates 10 fine-grained sectors into 5 high-level ones matching
the platform's official sector taxonomy:

  Mining and metals          (mining_metallurgy)
  Oil and gas                (oil_gas)
  Electric energy            (energy)
  Transport and comms        (transport_communications)
  Other                      (other)

All three language fields (RU / UZ-Cyrillic / EN) are populated for
every company and sector. Existing companies are matched by lowercase
ticker — UPDATE if found, INSERT if missing.

This migration is idempotent: re-running it produces the same end state.
Existing FK references (financial_reports, tasks, ratings, …) are
preserved because we never DELETE companies — only UPDATE.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0010_canonical_names"
down_revision: Union[str, None] = "0009_admin_users_perm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =====================================================================
# 5 canonical sectors (per platform's official taxonomy)
# =====================================================================

SECTORS = [
    # code,                         name_ru,                                     name_uz,                                     name_en,                              sort
    ("mining_metallurgy",           "Горно-металлургический сектор",             "Тоғ-кон металлургия",                       "Mining and metals",                   10),
    ("oil_gas",                     "Нефть и газ",                                "Нефть ва газ",                              "Oil and gas",                         20),
    ("energy",                      "Энергетика",                                 "Энергетика",                                "Electric energy",                     30),
    ("transport_communications",    "Транспорт и коммуникации",                  "Транспорт ва коммуникациялар",              "Transport and communications",        40),
    ("other",                       "Другой сектор",                              "Бошқа сектор",                              "Other sector",                        50),
]


# =====================================================================
# 22 canonical companies — Vladimir's authoritative list (2026-05).
# Format: (ticker, sector_code, name_ru, name_uz, name_en, name_short, sort)
# =====================================================================

COMPANIES = [
    # --- Mining and metals -------------------------------------------------------------------------------------------------------------
    ("ngmk", "mining_metallurgy",        "АО «Навоийский ГМК»",                          "“Навоий КМК” АЖ",                          '"Navoiy MMC" JSC',                              "НГМК",                10),
    ("nur",  "mining_metallurgy",        "ГП «Навоийуран»",                              "“Навоийуран” ДК",                          '"Navoiyuran" State Enterprise',                 "Навоийуран",          20),
    ("agmk", "mining_metallurgy",        "АО «Алмалыкский ГМК»",                         "“Олмалиқ КМК” АЖ",                         '"Almalyk MMC" JSC',                             "АГМК",                30),
    ("umk",  "mining_metallurgy",        "АО «Узметкомбинат»",                           "“Ўзметкомбинат” АЖ",                       '"Uzmetkombinat" JSC',                           "Узметкомбинат",       40),
    ("uug",  "mining_metallurgy",        "АО «Узбекуголь»",                              "“Ўзбеккўмир” АЖ",                          '"UzbekCoal" JSC',                               "Узбекуголь",          50),

    # --- Oil and gas -------------------------------------------------------------------------------------------------------------------
    ("ung",  "oil_gas",                  "АО «Узбекнефтегаз»",                            "“Ўзбекнефтгаз” АЖ",                        '"Uzbekneftegaz" JSC',                           "Узбекнефтегаз",       60),
    ("utg",  "oil_gas",                  "АО «Узтрансгаз»",                               "“Ўзтрансгаз” АЖ",                          '"Uztransgaz" JSC',                              "Узтрансгаз",          70),
    ("hgt",  "oil_gas",                  "АО «Худудгазтаъминот»",                         "“Ҳудудгазтаъминот” АЖ",                    '"Hududgaztaminot" JSC',                         "Худудгазтаъминот",    80),
    ("ugt",  "oil_gas",                  "АО «UzGasTrade»",                               "“UzGasTrade” АЖ",                          '"UzGasTrade" JSC',                              "UzGasTrade",          90),

    # --- Electric energy ---------------------------------------------------------------------------------------------------------------
    ("nes",  "energy",                   "АО «Национальные электрические сети Узбекистана»",  "“Ўзбекистон МЭТ” АЖ",                  '"National Electric Grids of Uzbekistan" JSC',   "НЭС",                100),
    ("tes",  "energy",                   "АО «Тепловые электрические станции»",           "“Иссиқлик электр станциялари” АЖ",         '"Thermal Power Plants" JSC',                    "ТЭС",                110),
    ("res",  "energy",                   "АО «Региональные электрические сети»",          "“Ҳудудий электр тармоқлари” АЖ",           '"Regional Electric Grids" JSC',                 "РЭС",                120),
    ("uge",  "energy",                   "АО «Узбекгидроэнерго»",                          "“Ўзбекгидроэнерго” АЖ",                    '"Uzbekgidroenergo" JSC',                        "Узгидроэнерго",      130),

    # --- Transport and communications --------------------------------------------------------------------------------------------------
    ("uty",  "transport_communications", "АО «Узбeкистон тeмир йуллари»",                "“Ўзбекистон темир йўллари” АЖ",            '"Uzbekistan Railways" JSC',                     "УТЙ",                140),
    ("uhy",  "transport_communications", "АО «Uzbekistan Airways»",                       "“Uzbekistan airways” АЖ",                  '"Uzbekistan Airways" JSC',                      "Uzairways",          150),
    ("uap",  "transport_communications", "АО «Uzbekistan Airports»",                      "“Uzbekistan Airports” АЖ",                 '"Uzbekistan Airports" JSC',                     "Uzairports",         160),
    ("tst",  "transport_communications", "АО «Тошшахартрансхизмат»",                      "“Тошшаҳартрансхизмат” АЖ",                 '"Toshshahartransxizmat" JSC',                   "ТШТХ",               170),
    ("utc",  "transport_communications", "АО «Узбектелеком»",                              "“Ўзбектелеком” АЖ",                        '"Uzbektelecom" JSC',                            "Узбектелеком",       180),
    ("upt",  "transport_communications", "АО «Узбекистон почтаси»",                       "“Ўзбекистон почтаси” АЖ",                  '"UzPost" JSC',                                  "Узпочта",            190),

    # --- Other -------------------------------------------------------------------------------------------------------------------------
    ("uks",  "other",                    "АО «Узкимёсаноат»",                             "“Ўзкимёсаноат” АЖ",                        '"Uzkimyosanoat" JSC',                           "Узкимёсаноат",       200),
    ("naz",  "other",                    "АО «Навоийазот»",                                "“Навоийазот” АЖ",                          '"Navoiazot" JSC',                                "Навоийазот",         210),
    ("uas",  "other",                    "АО «Узавтосаноат»",                              "“Ўзавтосаноат” АЖ",                        '"Uzavtosanoat" JSC',                            "Узавтосаноат",       220),
]


def _esc(s: str | None) -> str:
    """Escape single quote for SQL literal — there is no SQLi risk here as
    inputs are hardcoded constants, but doubling quotes is required to
    embed text containing apostrophes ('It's a long day' → 'It''s a long day')."""
    if s is None:
        return "NULL"
    return "'" + s.replace("'", "''") + "'"


def upgrade() -> None:
    # =================================================================
    # Step 1: Upsert canonical sectors
    # =================================================================
    for code, name_ru, name_uz, name_en, sort in SECTORS:
        op.execute(f"""
            INSERT INTO sectors (id, code, name_ru, name_uz, name_en, sort_order, created_at, updated_at)
            VALUES (gen_random_uuid(), {_esc(code)}, {_esc(name_ru)}, {_esc(name_uz)}, {_esc(name_en)}, {sort}, NOW(), NOW())
            ON CONFLICT (code) DO UPDATE SET
                name_ru    = EXCLUDED.name_ru,
                name_uz    = EXCLUDED.name_uz,
                name_en    = EXCLUDED.name_en,
                sort_order = EXCLUDED.sort_order,
                updated_at = NOW();
        """)

    # =================================================================
    # Step 2: Migrate companies that pointed to OLD sectors → consolidated ones
    # (mining + metallurgy → mining_metallurgy; chemistry + telecom → other / transport_communications)
    # =================================================================
    op.execute("""
        UPDATE companies SET sector_id = (SELECT id FROM sectors WHERE code = 'mining_metallurgy')
        WHERE sector_id IN (SELECT id FROM sectors WHERE code IN ('mining', 'metallurgy'));

        UPDATE companies SET sector_id = (SELECT id FROM sectors WHERE code = 'transport_communications')
        WHERE sector_id IN (SELECT id FROM sectors WHERE code IN ('transport', 'telecom'));

        UPDATE companies SET sector_id = (SELECT id FROM sectors WHERE code = 'other')
        WHERE sector_id IN (SELECT id FROM sectors WHERE code IN ('chemistry', 'finance', 'agro'));
    """)

    # =================================================================
    # Step 3: Remove unused legacy sectors. Companies have been re-pointed
    # above; the FK ON DELETE SET NULL would handle stragglers safely
    # but in fact every row should now point to one of the 5 canonical
    # sectors, so the WHERE clause leaves only orphan rows to be deleted.
    # =================================================================
    op.execute("""
        DELETE FROM sectors
        WHERE code NOT IN ('mining_metallurgy', 'oil_gas', 'energy',
                           'transport_communications', 'other')
          AND id NOT IN (SELECT sector_id FROM companies WHERE sector_id IS NOT NULL);
    """)

    # =================================================================
    # Step 4: Upsert canonical companies
    # =================================================================
    for code, sector_code, name_ru, name_uz, name_en, name_short, sort in COMPANIES:
        op.execute(f"""
            INSERT INTO companies
              (id, code, name_ru, name_uz, name_en, name_short,
               sector_id, legal_form, is_active, is_custom, sort_order, created_at, updated_at)
            VALUES (
              gen_random_uuid(),
              {_esc(code)},
              {_esc(name_ru)},
              {_esc(name_uz)},
              {_esc(name_en)},
              {_esc(name_short)},
              (SELECT id FROM sectors WHERE code = {_esc(sector_code)}),
              CASE WHEN {_esc(name_ru)} LIKE 'ГП %' THEN 'ГП' ELSE 'АО' END,
              true, false,
              {sort},
              NOW(), NOW()
            )
            ON CONFLICT (code) DO UPDATE SET
                name_ru    = EXCLUDED.name_ru,
                name_uz    = EXCLUDED.name_uz,
                name_en    = EXCLUDED.name_en,
                name_short = EXCLUDED.name_short,
                sector_id  = EXCLUDED.sector_id,
                legal_form = EXCLUDED.legal_form,
                sort_order = EXCLUDED.sort_order,
                is_active  = true,
                updated_at = NOW();
        """)


def downgrade() -> None:
    # No-op: this is a content migration, not a schema change.
    # Reverting names would require restoring the previous text, which is
    # not preserved. Run a fresh seed if rollback is required.
    pass
