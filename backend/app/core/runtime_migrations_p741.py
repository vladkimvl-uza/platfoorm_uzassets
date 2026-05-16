"""
Pack 7.41 runtime migrations — self-heal for credit-scenario tables.

Idempotent additive self-heal for the 4 new Pack 7.41 tables + amortization seed.

Integration:
  Call `await pack_741_self_heal(db)` from the bootstrap/startup hook
  that already runs prior pack migrations.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


DDL_LOAN_REPAYMENTS = """
CREATE TABLE IF NOT EXISTS loan_repayments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    loan_id UUID NOT NULL REFERENCES cp_loans(id) ON DELETE CASCADE,
    period_year INTEGER NOT NULL,
    period_quarter INTEGER NOT NULL CHECK (period_quarter BETWEEN 1 AND 4),
    scheduled_amount_currency NUMERIC(20,2),
    scheduled_amount_usd NUMERIC(20,2),
    actual_paid_amount_currency NUMERIC(20,2),
    actual_paid_amount_usd NUMERIC(20,2),
    status VARCHAR(16) NOT NULL DEFAULT 'scheduled',
    payment_date DATE,
    is_custom_schedule BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_repay_loan_period UNIQUE (loan_id, period_year, period_quarter)
);
CREATE INDEX IF NOT EXISTS ix_loan_repayments_loan_id ON loan_repayments(loan_id);
CREATE INDEX IF NOT EXISTS ix_loan_repayments_period_year ON loan_repayments(period_year);
CREATE INDEX IF NOT EXISTS ix_loan_repayments_status ON loan_repayments(status);
CREATE INDEX IF NOT EXISTS ix_repay_period ON loan_repayments(period_year, period_quarter);
CREATE INDEX IF NOT EXISTS ix_repay_status_period ON loan_repayments(status, period_year);
"""

DDL_SCENARIO = """
CREATE TABLE IF NOT EXISTS credit_portfolio_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    macro_scenario_key VARCHAR(64) NOT NULL UNIQUE,
    name_ru VARCHAR(255),
    state_forgiveness_pct NUMERIC(6,4),
    refinance_rate_delta_pp NUMERIC(6,4),
    default_rate_pct NUMERIC(6,4),
    repayment_acceleration_pct NUMERIC(6,4),
    risk_formula_text TEXT,
    risk_rr_by_lender JSONB NOT NULL DEFAULT '{}'::jsonb,
    extra JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_credit_portfolio_scenarios_macro_key
    ON credit_portfolio_scenarios(macro_scenario_key);
"""

DDL_LOAN_SCENARIO = """
CREATE TABLE IF NOT EXISTS credit_portfolio_loan_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id UUID NOT NULL REFERENCES credit_portfolio_scenarios(id) ON DELETE CASCADE,
    loan_id UUID NOT NULL REFERENCES cp_loans(id) ON DELETE CASCADE,
    forgiveness_pct NUMERIC(6,4),
    rate_override NUMERIC(10,6),
    rescheduled_to DATE,
    default_probability NUMERIC(6,4),
    partial_repayment_pct NUMERIC(6,4),
    custom_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_loan_scenario UNIQUE (scenario_id, loan_id)
);
CREATE INDEX IF NOT EXISTS ix_loan_scenarios_scenario_id
    ON credit_portfolio_loan_scenarios(scenario_id);
CREATE INDEX IF NOT EXISTS ix_loan_scenarios_loan_id
    ON credit_portfolio_loan_scenarios(loan_id);
"""

DDL_CUSTOM_INDICATOR = """
CREATE TABLE IF NOT EXISTS credit_custom_indicators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(64) NOT NULL UNIQUE,
    name_ru VARCHAR(255) NOT NULL,
    input_type VARCHAR(16) NOT NULL,
    min_value NUMERIC(20,6),
    max_value NUMERIC(20,6),
    current_value NUMERIC(20,6),
    formula_text TEXT,
    aggregation VARCHAR(16),
    source_metric TEXT,
    tooltip_ru TEXT,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_credit_custom_indicators_key
    ON credit_custom_indicators(key);
"""


SEED_SCENARIOS = [
    {
        "macro_scenario_key": "base",
        "name_ru": "Базовый сценарий",
        "state_forgiveness_pct": "0.00",
        "refinance_rate_delta_pp": "0.00",
        "default_rate_pct": "0.02",
        "repayment_acceleration_pct": "0.00",
        "risk_rr_by_lender": '{"state":0.75,"local":0.50,"foreign":0.35,"bond":0.40,"guaranteed_override":0.85}',
    },
    {
        "macro_scenario_key": "optimistic",
        "name_ru": "Оптимистичный сценарий",
        "state_forgiveness_pct": "0.15",
        "refinance_rate_delta_pp": "-0.015",
        "default_rate_pct": "0.01",
        "repayment_acceleration_pct": "0.10",
        "risk_rr_by_lender": '{"state":0.80,"local":0.55,"foreign":0.40,"bond":0.45,"guaranteed_override":0.90}',
    },
    {
        "macro_scenario_key": "pessimistic",
        "name_ru": "Пессимистичный сценарий",
        "state_forgiveness_pct": "0.00",
        "refinance_rate_delta_pp": "0.025",
        "default_rate_pct": "0.05",
        "repayment_acceleration_pct": "-0.10",
        "risk_rr_by_lender": '{"state":0.70,"local":0.40,"foreign":0.30,"bond":0.35,"guaranteed_override":0.80}',
    },
]


async def pack_741_self_heal(db: AsyncSession) -> dict:
    """Idempotently create Pack 7.41 tables + seed defaults + amortization."""
    report = {"tables_created": [], "scenarios_seeded": 0, "amortization_rows_inserted": 0}

    for name, ddl in [
        ("loan_repayments", DDL_LOAN_REPAYMENTS),
        ("credit_portfolio_scenarios", DDL_SCENARIO),
        ("credit_portfolio_loan_scenarios", DDL_LOAN_SCENARIO),
        ("credit_custom_indicators", DDL_CUSTOM_INDICATOR),
    ]:
        try:
            for stmt in ddl.split(";"):
                stmt = stmt.strip()
                if stmt:
                    await db.execute(text(stmt))
            await db.commit()
            report["tables_created"].append(name)
        except Exception as e:
            log.warning("Pack 7.41 DDL for %s failed: %s", name, e)
            await db.rollback()

    for sc in SEED_SCENARIOS:
        try:
            await db.execute(
                text(
                    "INSERT INTO credit_portfolio_scenarios "
                    "(macro_scenario_key, name_ru, state_forgiveness_pct, "
                    " refinance_rate_delta_pp, default_rate_pct, "
                    " repayment_acceleration_pct, risk_rr_by_lender) "
                    "VALUES (:k,:n,:f,:r,:d,:a, CAST(:rr AS JSONB)) "
                    "ON CONFLICT (macro_scenario_key) DO NOTHING"
                ),
                {
                    "k": sc["macro_scenario_key"], "n": sc["name_ru"],
                    "f": sc["state_forgiveness_pct"], "r": sc["refinance_rate_delta_pp"],
                    "d": sc["default_rate_pct"], "a": sc["repayment_acceleration_pct"],
                    "rr": sc["risk_rr_by_lender"],
                },
            )
            report["scenarios_seeded"] += 1
        except Exception as e:
            log.warning("Pack 7.41 seed %s failed: %s", sc["macro_scenario_key"], e)
            await db.rollback()
    await db.commit()

    try:
        from app.services.loan_amortization import seed_schedules_for_all_loans
        inserted = await seed_schedules_for_all_loans(db, as_of=date.today())
        report["amortization_rows_inserted"] = inserted
    except Exception as e:
        log.warning("Pack 7.41 amortization seed failed: %s", e)

    log.info("Pack 7.41 self-heal: %s", report)
    return report
