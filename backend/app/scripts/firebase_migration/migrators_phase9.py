"""Phase 9: ESG metrics seed migrator.

Source of truth: hardcoded ESG_DATA object embedded in monolith index.html
(line ~52469). Firebase has no ESG metric scores — only esgIssues (global tags)
and esgYearsTracked (meta).

This migrator reads the embedded ESG_SEED constant (extracted from monolith)
and writes 11 companies × ~14 metrics into the esg_metrics table.

Year for all values: 2025 (the snapshot year of monolith ESG_DATA).
sfScore2025 / sfScore2026 are split into two rows with year=2025 and year=2026.

All non-numeric fields (rating, trend, iso[], isoPlanned[], esgRating,
highlights[]) are stored in a single metadata row with metric_code='_meta'
and the full payload in `extra` JSONB.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, delete

from app.models.company import Company
from app.models.esg import ESGMetric
from .base import Migrator, MigrationContext

log = logging.getLogger(__name__)


# =====================================================================
# Embedded ESG_DATA seed (extracted from monolith line ~52469)
# 11 companies, snapshot year = 2025 (sfScore2026 → year=2026 row)
# =====================================================================

ESG_SEED: dict[str, dict[str, Any]] = {
    "НГМК": {
        "sector": "mining",
        "e": 72,
        "s": 78,
        "g": 75,
        "rating": "54",
        "trend": "+3",
        "sfScore2025": 51,
        "sfScore2026": 54,
        "iso": [
            "ISO 9001:2015",
            "ISO 14001:2015",
            "ISO 45001:2018",
            "ISO 50001:2018"
        ],
        "isoPlanned": [
            "GRI Standards"
        ],
        "esgRating": "Sustainable Fitch",
        "esgRatingYear": 2024,
        "co2": 420,
        "water": 186,
        "waste": 1250,
        "renewPct": 21,
        "envFines": 0,
        "employees": 27500,
        "womenMgmt": 12,
        "ltifr": 1.4,
        "training": 38,
        "highlights": [
            "21% энергии из ВИЭ к концу 2025",
            "Программа водосбережения 2024-2030 (36 млн м³)",
            "Сертификация SGS по ISO 14001",
            "ESG рейтинг от Sustainable Fitch (2024)",
            "Подготовка к IPO — усиление ESG-отчётности",
            "Отчётность GRI Standards"
        ]
    },
    "АГМК": {
        "sector": "mining",
        "e": 58,
        "s": 68,
        "g": 62,
        "rating": "59",
        "trend": "+3",
        "sfScore2025": 56,
        "sfScore2026": 59,
        "iso": [
            "ISO 9001:2015",
            "ISO 14001:2015",
            "ISO 45001:2018"
        ],
        "isoPlanned": [
            "ISO 50001",
            "ESG рейтинг Sustainable Fitch"
        ],
        "esgRating": "Sustainable Fitch Level 3",
        "esgRatingYear": 2024,
        "co2": 380,
        "water": 145,
        "waste": 980,
        "renewPct": 5,
        "envFines": 1,
        "employees": 22000,
        "womenMgmt": 10,
        "ltifr": 2.3,
        "training": 28,
        "highlights": [
            "ESG рейтинг 3 уровня от Sustainable Fitch",
            "Планы по внедрению ISO 50001",
            "Модернизация очистных сооружений"
        ]
    },
    "Узбекнефтегаз": {
        "sector": "oilgas",
        "e": 45,
        "s": 62,
        "g": 55,
        "rating": "50",
        "trend": "+2",
        "sfScore2025": 50,
        "iso": [
            "ISO 9001:2015",
            "ISO 14001:2015"
        ],
        "isoPlanned": [
            "ISO 45001",
            "ESG рейтинг",
            "Декарбонизация 2030"
        ],
        "co2": 890,
        "water": 95,
        "waste": 340,
        "renewPct": 2,
        "envFines": 3,
        "employees": 42000,
        "womenMgmt": 8,
        "ltifr": 3.1,
        "training": 22,
        "highlights": [
            "Планируется получение ESG рейтинга",
            "Программа сокращения попутного сжигания газа",
            "Внедрение ISO 45001 в процессе"
        ]
    },
    "Uzbekistan Airways": {
        "sector": "transport",
        "e": 48,
        "s": 72,
        "g": 65,
        "rating": "B",
        "trend": "+1",
        "iso": [
            "ISO 9001:2015",
            "IOSA"
        ],
        "isoPlanned": [
            "ISO 14001",
            "ESG рейтинг",
            "CORSIA"
        ],
        "co2": 210,
        "water": 3,
        "waste": 12,
        "renewPct": 0,
        "envFines": 0,
        "employees": 8500,
        "womenMgmt": 22,
        "ltifr": 0.4,
        "training": 52,
        "highlights": [
            "Планируется ESG рейтинг",
            "Обновление флота — снижение выбросов на 15%",
            "Программа CORSIA по углеродной нейтральности",
            "Высокая доля женщин в управлении (22%)"
        ]
    },
    "Uzbekistan Airports": {
        "sector": "transport",
        "e": 42,
        "s": 65,
        "g": 58,
        "rating": "B-",
        "trend": "+2",
        "iso": [
            "ISO 9001:2015"
        ],
        "isoPlanned": [
            "ISO 14001",
            "ISO 45001",
            "ESG рейтинг"
        ],
        "co2": 85,
        "water": 12,
        "waste": 28,
        "renewPct": 3,
        "envFines": 0,
        "employees": 6200,
        "womenMgmt": 15,
        "ltifr": 1.2,
        "training": 30,
        "highlights": [
            "Планируется ESG рейтинг",
            "Модернизация аэропортов — энергоэффективность",
            "Солнечные панели в аэропорту Ташкента"
        ]
    },
    "UzTelecom": {
        "sector": "other",
        "e": 55,
        "s": 70,
        "g": 68,
        "rating": "B+",
        "trend": "+4",
        "iso": [
            "ISO 9001:2015",
            "ISO 27001:2013"
        ],
        "isoPlanned": [
            "ISO 14001",
            "ESG стратегия"
        ],
        "co2": 18,
        "water": 2,
        "waste": 5,
        "renewPct": 8,
        "envFines": 0,
        "employees": 11000,
        "womenMgmt": 18,
        "ltifr": 0.3,
        "training": 45,
        "highlights": [
            "Запуск 5.5G технологий (2024)",
            "Цифровизация — сокращение бумажного документооборота",
            "Высокий уровень обучения сотрудников"
        ]
    },
    "ТЭС": {
        "sector": "energy",
        "e": 38,
        "s": 60,
        "g": 52,
        "rating": "C+",
        "trend": "+1",
        "iso": [
            "ISO 9001:2015"
        ],
        "isoPlanned": [
            "ISO 14001",
            "ISO 45001",
            "Модернизация генерации"
        ],
        "co2": 1200,
        "water": 320,
        "waste": 180,
        "renewPct": 0,
        "envFines": 2,
        "employees": 18000,
        "womenMgmt": 7,
        "ltifr": 2.8,
        "training": 18,
        "highlights": [
            "Крупнейший источник выбросов CO₂ в портфеле",
            "Планы модернизации ТЭС на газ",
            "Необходимо внедрение ISO 14001"
        ]
    },
    "РЭС": {
        "sector": "energy",
        "e": 40,
        "s": 58,
        "g": 50,
        "rating": "C+",
        "trend": "0",
        "iso": [
            "ISO 9001:2015"
        ],
        "isoPlanned": [
            "ISO 14001",
            "ISO 45001"
        ],
        "co2": 45,
        "water": 8,
        "waste": 35,
        "renewPct": 0,
        "envFines": 1,
        "employees": 28000,
        "womenMgmt": 6,
        "ltifr": 3.5,
        "training": 15,
        "highlights": [
            "Высокий травматизм — необходим ISO 45001",
            "Низкая доля женщин в управлении",
            "Планы по снижению потерь в сетях"
        ]
    },
    "НЭС": {
        "sector": "energy",
        "e": 42,
        "s": 55,
        "g": 48,
        "rating": "C",
        "trend": "-1",
        "iso": [],
        "isoPlanned": [
            "ISO 9001",
            "ISO 14001",
            "ISO 45001"
        ],
        "co2": 35,
        "water": 5,
        "waste": 22,
        "renewPct": 0,
        "envFines": 1,
        "employees": 15000,
        "womenMgmt": 5,
        "ltifr": 4.0,
        "training": 12,
        "highlights": [
            "Нет ISO сертификаций — критический разрыв",
            "Самый высокий LTIFR в портфеле",
            "Необходима комплексная ESG-трансформация"
        ]
    },
    "Навоийазот": {
        "sector": "other",
        "e": 35,
        "s": 55,
        "g": 45,
        "rating": "C",
        "trend": "0",
        "iso": [
            "ISO 9001:2015"
        ],
        "isoPlanned": [
            "ISO 14001"
        ],
        "co2": 520,
        "water": 78,
        "waste": 210,
        "renewPct": 0,
        "envFines": 2,
        "employees": 5800,
        "womenMgmt": 9,
        "ltifr": 2.5,
        "training": 20,
        "highlights": [
            "Высокие выбросы для химической отрасли",
            "Необходима экологическая модернизация"
        ]
    },
    "Узметкомбинат": {
        "sector": "mining",
        "e": 32,
        "s": 52,
        "g": 40,
        "rating": "C-",
        "trend": "-2",
        "iso": [],
        "isoPlanned": [
            "ISO 9001",
            "ISO 14001",
            "ISO 45001"
        ],
        "co2": 680,
        "water": 95,
        "waste": 450,
        "renewPct": 0,
        "envFines": 3,
        "employees": 8200,
        "womenMgmt": 4,
        "ltifr": 3.8,
        "training": 14,
        "highlights": [
            "Нет ISO сертификаций",
            "Высокие выбросы и экологические штрафы",
            "Необходима полная ESG-трансформация"
        ]
    }
}


# =====================================================================
# Field → metric mapping
# =====================================================================
# (field_name, pillar, metric_code, metric_name, unit)
# 'value' will be Decimal-converted from the seed value at write time.
# Fields not in this list are passed through to the _meta row's `extra`.

NUMERIC_METRICS: list[tuple[str, str, str, str, Optional[str]]] = [
    # --- E pillar ---
    ("e",          "E", "e_score",            "E-балл (Environmental)",       "очки/100"),
    ("co2",        "E", "co2_emissions",      "Выбросы CO₂",                  "тыс. тонн"),
    ("water",      "E", "water_consumption",  "Водопотребление",              "млн м³"),
    ("waste",      "E", "waste_generation",   "Отходы производства",          "тыс. тонн"),
    ("renewPct",   "E", "renewable_pct",      "Доля возобновляемых источников", "%"),
    ("envFines",   "E", "env_fines_count",    "Количество экологических штрафов", "шт"),
    # --- S pillar ---
    ("s",          "S", "s_score",            "S-балл (Social)",              "очки/100"),
    ("employees",  "S", "employees_count",    "Численность персонала",        "чел"),
    ("womenMgmt",  "S", "women_in_management", "Женщины в управлении",        "%"),
    ("ltifr",      "S", "ltifr",              "LTIFR (травматизм)",           "случаев/млн ч"),
    ("training",   "S", "training_hours",     "Часы обучения на сотрудника",  "ч/год"),
    # --- G pillar ---
    ("g",          "G", "g_score",            "G-балл (Governance)",          "очки/100"),
]

# Sustainable Fitch scores get split into 2 rows (year 2025 / year 2026)
SF_SCORE_FIELDS = [
    ("sfScore2025", 2025, "sf_score", "Sustainable Fitch — итоговый ESG-балл", "очки"),
    ("sfScore2026", 2026, "sf_score", "Sustainable Fitch — итоговый ESG-балл", "очки"),
]

# Default snapshot year for all main metrics
SNAPSHOT_YEAR = 2025

# Metadata fields (non-numeric) → packed into _meta row's extra JSONB
META_FIELDS = ["rating", "trend", "iso", "isoPlanned",
               "esgRating", "esgRatingYear", "highlights", "sector"]


# =====================================================================
# Translit aliases for company names
# =====================================================================
# Maps ESG_SEED keys (mostly Russian abbreviations + a few English) to
# Company lookup keys. Reuses Phase 6 pattern.
_ESG_NAME_TO_CODE = {
    "нгмк": "ngmk",
    "агмк": "agmk",
    "узбекнефтегаз": "ung",
    "uzbekistan airways": "uhy",
    "uzbekistan airports": "uap",
    "uztelecom": "utc",
    "тэс": "tes",
    "рэс": "res",
    "нэс": "nes",
    "навоийазот": "naz",
    "узметкомбинат": "umk",
}


async def _build_company_lookup(ctx: MigrationContext) -> dict[str, Company]:
    """Build a lookup keyed by code, name_ru, name_short, name_en."""
    rows_q = await ctx.db.execute(select(Company))
    rows = rows_q.scalars().all()
    lookup: dict[str, Company] = {}
    by_code: dict[str, Company] = {}

    for c in rows:
        if c.code:
            by_code[c.code.lower().strip()] = c
        for fld in ("code", "name_ru", "name_short", "name_uz", "name_en"):
            v = getattr(c, fld, None)
            if v:
                key = v.lower().strip()
                lookup[key] = c
                stripped = key.replace("«", "").replace("»", "").replace('"', "")
                for prefix in ("ао ", "ао_", "оао "):
                    if stripped.startswith(prefix):
                        stripped = stripped[len(prefix):].strip()
                if stripped:
                    lookup[stripped] = c

    # Overlay explicit ESG seed name aliases
    for alias, code in _ESG_NAME_TO_CODE.items():
        co = by_code.get(code)
        if co:
            lookup[alias] = co
    return lookup


def _to_decimal(v: Any) -> Optional[Decimal]:
    """Numeric coercion for seed values. Returns None for None/'' /non-numeric."""
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


# =====================================================================
# Migrator
# =====================================================================

class ESGMetricsMigrator(Migrator):
    name = "esg_metrics"
    firebase_path = "<embedded ESG_DATA seed>"

    async def fetch(self, ctx: MigrationContext) -> dict[str, Any]:
        """Returns embedded seed (no Firebase fetch)."""
        return dict(ESG_SEED)

    async def apply(self, ctx: MigrationContext) -> MigratorResult:
        seed = await self.fetch(ctx)
        if not isinstance(seed, dict) or not seed:
            pass

        lookup = await _build_company_lookup(ctx)

        # Wipe existing rows for the snapshot years (idempotent rerun)
        years_to_clear = {SNAPSHOT_YEAR} | {yr for _, yr, _, _, _ in SF_SCORE_FIELDS}
        for year in years_to_clear:
            await ctx.db.execute(delete(ESGMetric).where(ESGMetric.year == year))
        await ctx.db.flush()

        created = 0
        skipped = 0
        skip_reasons: list[str] = []

        for co_name, fields in seed.items():
            if not isinstance(fields, dict):
                continue

            co = lookup.get(co_name.lower().strip())
            if co is None:
                skipped += 1
                skip_reasons.append(f"company '{co_name}' not in PG")
                continue

            # 1) numeric metrics for SNAPSHOT_YEAR
            for fb_field, pillar, code, name_ru, unit in NUMERIC_METRICS:
                val = _to_decimal(fields.get(fb_field))
                if val is None:
                    continue
                metric = ESGMetric(
                    company_id=co.id,
                    year=SNAPSHOT_YEAR,
                    pillar=pillar,
                    metric_code=code,
                    metric_name=name_ru,
                    value=val,
                    unit=unit,
                )
                ctx.db.add(metric)
                created += 1

            # 2) Sustainable Fitch scores: one row per year
            for fb_field, year, code, name_ru, unit in SF_SCORE_FIELDS:
                val = _to_decimal(fields.get(fb_field))
                if val is None:
                    continue
                metric = ESGMetric(
                    company_id=co.id,
                    year=year,
                    pillar="G",
                    metric_code=code,
                    metric_name=name_ru,
                    value=val,
                    unit=unit,
                )
                ctx.db.add(metric)
                created += 1

            # 3) Meta row with non-numeric ESG context (rating, trend, ISO, highlights)
            meta_payload = {k: fields.get(k) for k in META_FIELDS if k in fields}
            if meta_payload:
                meta = ESGMetric(
                    company_id=co.id,
                    year=SNAPSHOT_YEAR,
                    pillar="G",          # G is the natural pillar for governance/rating meta
                    metric_code="_meta",
                    metric_name="ESG meta (rating, trend, ISO, highlights)",
                    value=None,
                    unit=None,
                    extra=meta_payload,
                )
                ctx.db.add(meta)
                created += 1

        await ctx.db.flush()
        log.info(
            "  ✓ esg_metrics: %d rows seeded across %d companies, %d skipped",
            created, len(seed) - skipped, skipped,
        )
