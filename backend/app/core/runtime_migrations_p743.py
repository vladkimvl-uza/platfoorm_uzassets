"""Pack 7.43 — Runtime migration + sector-default seed for elasticity tables."""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS elasticity_coefficients (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        scenario_id UUID REFERENCES macro_scenarios(id) ON DELETE CASCADE,
        company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
        macro_factor VARCHAR(64) NOT NULL,
        target_metric VARCHAR(64) NOT NULL,
        beta NUMERIC(10, 4) NOT NULL,
        notes TEXT,
        source VARCHAR(32) NOT NULL DEFAULT 'manual',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_elasticity_scope UNIQUE (scenario_id, company_id, macro_factor, target_metric)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_elasticity_scenario ON elasticity_coefficients (scenario_id)",
    "CREATE INDEX IF NOT EXISTS ix_elasticity_company ON elasticity_coefficients (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_elasticity_macro_target ON elasticity_coefficients (macro_factor, target_metric)",
    "CREATE INDEX IF NOT EXISTS ix_elasticity_factor ON elasticity_coefficients (macro_factor)",
    """
    CREATE TABLE IF NOT EXISTS project_financial_effects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        effective_year INTEGER NOT NULL,
        target_metric VARCHAR(64) NOT NULL,
        delta_value_uzs_mln NUMERIC(20, 2),
        delta_pct NUMERIC(8, 4),
        probability_pct NUMERIC(5, 2) NOT NULL DEFAULT 100,
        confidence VARCHAR(16) NOT NULL DEFAULT 'medium',
        notes TEXT,
        extra JSONB,
        created_by VARCHAR(255),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_project_effect_year_metric UNIQUE (project_id, effective_year, target_metric)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_project_effect_project ON project_financial_effects (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_project_effect_year ON project_financial_effects (effective_year)",
]


# ─── Sector-based defaults ───
# β-коэффициенты — на сколько % изменится metric при изменении factor на 1%.
# Знак: положительный = в одну сторону, отрицательный = в обратную.
SECTOR_DEFAULTS = {
    # Mining (горнодобыча): выручка экспортная, чувствительна к USD и ценам сырья
    "mining": {
        "usd_rate→revenue": 0.85,
        "usd_rate→opex": 0.30,
        "inflation_pct→opex": 0.50,
        "cb_rate_pct→capex": -0.40,
        "gdp_growth_pct→revenue": 0.50,
        "oil_price_brent→opex": 0.20,
    },
    # Oil & Gas: сильная привязка к мировым ценам нефти
    "oil_gas": {
        "usd_rate→revenue": 0.90,
        "usd_rate→opex": 0.40,
        "oil_price_brent→revenue": 0.80,
        "inflation_pct→opex": 0.40,
        "cb_rate_pct→capex": -0.30,
        "gdp_growth_pct→revenue": 0.40,
    },
    # Energy / utilities: внутренний рынок, сильная зависимость от инфляции и ставки
    "energy": {
        "usd_rate→revenue": 0.20,
        "usd_rate→opex": 0.50,
        "inflation_pct→opex": 0.60,
        "inflation_pct→revenue": 0.40,
        "cb_rate_pct→capex": -0.50,
        "gdp_growth_pct→revenue": 0.50,
    },
    # Transport: ВВП-чувствительный сектор
    "transport": {
        "usd_rate→opex": 0.40,
        "inflation_pct→opex": 0.50,
        "cb_rate_pct→capex": -0.30,
        "gdp_growth_pct→revenue": 0.90,
        "oil_price_brent→opex": 0.60,
    },
    # Default (для всего остального)
    "_default": {
        "usd_rate→revenue": 0.30,
        "usd_rate→opex": 0.30,
        "inflation_pct→opex": 0.40,
        "cb_rate_pct→capex": -0.30,
        "gdp_growth_pct→revenue": 0.50,
    },
}


async def _seed_sector_defaults(db: AsyncSession) -> int:
    """Insert (NULL scenario, NULL company) rows from _default if missing.
    Sector-specific rows would require knowing each company's sector — left
    for the user to fill via the UI."""
    inserted = 0
    defaults = SECTOR_DEFAULTS["_default"]
    for combo, beta in defaults.items():
        factor, metric = combo.split("→")
        # Check if global default exists
        check = await db.execute(text(
            "SELECT 1 FROM elasticity_coefficients "
            "WHERE scenario_id IS NULL AND company_id IS NULL "
            "AND macro_factor = :f AND target_metric = :m"
        ), {"f": factor, "m": metric})
        if check.first():
            continue
        await db.execute(text(
            "INSERT INTO elasticity_coefficients "
            "(scenario_id, company_id, macro_factor, target_metric, beta, source, notes) "
            "VALUES (NULL, NULL, :f, :m, :b, 'seed_sector_default', "
            "'Глобальный дефолт. Перебивается на уровне компании или сценария.')"
        ), {"f": factor, "m": metric, "b": beta})
        inserted += 1
    await db.commit()
    return inserted


async def pack_743_self_heal(db: AsyncSession) -> dict:
    """Idempotent self-heal: create tables + seed defaults."""
    report = {"tables_created": [], "rows_seeded": 0, "errors": []}

    for stmt in DDL_STATEMENTS:
        try:
            await db.execute(text(stmt))
        except Exception as e:
            log.warning("Pack 7.43 DDL failed: %s", str(e)[:200])
            report["errors"].append({"sql": stmt[:80], "error": str(e)[:200]})
            await db.rollback()
            continue
    try:
        await db.commit()
    except Exception as e:
        log.warning("Pack 7.43 commit failed: %s", e)
        await db.rollback()

    # Check tables exist
    for tname in ("elasticity_coefficients", "project_financial_effects"):
        try:
            result = await db.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
            ), {"t": tname})
            if result.scalar():
                report["tables_created"].append(tname)
        except Exception:
            pass

    # Seed defaults
    try:
        n = await _seed_sector_defaults(db)
        report["rows_seeded"] = n
    except Exception as e:
        log.warning("Pack 7.43 seed failed: %s", e)
        report["errors"].append({"seed_error": str(e)[:200]})
        await db.rollback()

    log.info("Pack 7.43 self-heal: %s", report)
    return report
