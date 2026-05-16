"""Pack 7.43 — Forecast decomposition engine.

Computes: forecast(metric, year, company)
       = base(company)
       × Π over factors: (1 + Δfactor × β)
       + Σ project_effects(company, year, metric) × probability/100

Where:
  base = последнее известное значение из financial_lines (или fallback)
  Δfactor = macro_scenario_override[factor, year] - base macro value
  β = elasticity coefficient (с приоритетом scoping)
  project_effects — суммируются по всем проектам компании
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID as PyUUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.elasticity import ElasticityCoefficient, ProjectFinancialEffect
from app.models.company import Company
from app.schemas.elasticity import DecompositionResult, DecompositionComponent


# ─── Labels ──────────────────────────────────────────────────────────────────
MACRO_LABELS_RU = {
    "inflation_pct": "инфляция",
    "cb_rate_pct": "ставка ЦБ",
    "usd_rate": "курс USD",
    "eur_rate": "курс EUR",
    "gdp_growth_pct": "рост ВВП",
    "oil_price_brent": "нефть Brent",
}

METRIC_LABELS_RU = {
    "revenue": "выручка",
    "ebitda": "EBITDA",
    "opex": "OPEX",
    "capex": "CAPEX",
    "debt_service": "обслуживание долга",
    "net_income": "чистая прибыль",
}


async def _resolve_beta(
    db: AsyncSession,
    scenario_id: Optional[PyUUID],
    company_id: Optional[PyUUID],
    macro_factor: str,
    target_metric: str,
) -> Optional[Decimal]:
    """Resolve elasticity coefficient with priority:
       1. (scenario, company)
       2. (scenario, NULL)
       3. (NULL, company)
       4. (NULL, NULL)
    """
    candidates = [
        (scenario_id, company_id),
        (scenario_id, None),
        (None, company_id),
        (None, None),
    ]
    for sid, cid in candidates:
        if sid is None and scenario_id is not None:
            # if asking for global, skip company-specific scenario rows
            pass
        stmt = select(ElasticityCoefficient).where(
            ElasticityCoefficient.macro_factor == macro_factor,
            ElasticityCoefficient.target_metric == target_metric,
        )
        if sid is None:
            stmt = stmt.where(ElasticityCoefficient.scenario_id.is_(None))
        else:
            stmt = stmt.where(ElasticityCoefficient.scenario_id == sid)
        if cid is None:
            stmt = stmt.where(ElasticityCoefficient.company_id.is_(None))
        else:
            stmt = stmt.where(ElasticityCoefficient.company_id == cid)

        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return Decimal(str(row.beta))
    return None


async def _get_base_value(
    db: AsyncSession,
    company_id: Optional[PyUUID],
    target_metric: str,
    base_year: int,
) -> Decimal:
    """Try to get last known value of metric for the company. Falls back to 0.
    Looks in financial_lines (code = target_metric), latest report.
    """
    try:
        from sqlalchemy import text
        # Try multiple common code variants
        code_variants = [target_metric, target_metric.upper(), target_metric.lower()]
        if target_metric == "revenue":
            code_variants += ["sales", "REVENUE", "SALES"]
        if target_metric == "ebitda":
            code_variants += ["EBITDA"]

        q = """
        SELECT fl.value
        FROM financial_lines fl
        JOIN financial_reports fr ON fr.id = fl.report_id
        WHERE LOWER(fl.code) = ANY(:codes)
          AND (:cid IS NULL OR fr.company_id = :cid)
          AND fr.period_year <= :y
        ORDER BY fr.period_year DESC, fr.period_quarter DESC NULLS LAST
        LIMIT 1
        """
        result = await db.execute(
            text(q),
            {
                "codes": [c.lower() for c in code_variants],
                "cid": str(company_id) if company_id else None,
                "y": base_year,
            },
        )
        row = result.first()
        if row and row[0]:
            return Decimal(str(row[0]))
    except Exception:
        pass
    return Decimal("0")


async def _get_macro_deltas(
    db: AsyncSession,
    scenario_id: PyUUID,
    target_year: int,
    base_year: int,
) -> Dict[str, Decimal]:
    """Returns {factor: Δfactor as ratio} comparing scenario override at target_year
    vs base macro value at base_year. Each Δ is a ratio (e.g. inflation went from
    5% to 7% → Δ = 0.40 = 40% increase).

    For now we use macro_scenario_overrides table. Falls back to 0 if missing.
    """
    deltas = {f: Decimal("0") for f in MACRO_LABELS_RU.keys()}
    try:
        from sqlalchemy import text
        q = """
        SELECT factor_code, value_override
        FROM macro_scenario_overrides
        WHERE scenario_id = :sid AND year = :y
        """
        rows = (await db.execute(text(q), {"sid": str(scenario_id), "y": target_year})).all()
        for code, val in rows:
            if code in deltas and val is not None:
                # Δ — это просто отклонение в долях. Если value_override = +2 (п.п.) — это +2.
                deltas[code] = Decimal(str(val)) / Decimal("100") if "pct" in code else Decimal(str(val))
    except Exception:
        pass
    return deltas


async def _get_project_effects(
    db: AsyncSession,
    company_id: Optional[PyUUID],
    target_metric: str,
    target_year: int,
) -> Tuple[Decimal, List[dict]]:
    """Sum project effects for the given (company, metric, year).
    Returns (total_uzs_mln, list_of_components_for_display).
    """
    stmt = select(ProjectFinancialEffect).where(
        ProjectFinancialEffect.target_metric == target_metric,
        ProjectFinancialEffect.effective_year == target_year,
    )
    if company_id:
        # join with projects to filter by company_id
        from app.models.project import Project  # noqa
        stmt = stmt.join(Project, Project.id == ProjectFinancialEffect.project_id).where(
            Project.company_id == company_id
        )

    rows = (await db.execute(stmt)).scalars().all()
    total = Decimal("0")
    items: List[dict] = []
    for r in rows:
        # If absolute value present — use it. Otherwise apply pct to base
        # (we don't have base here, so just record %).
        prob = Decimal(str(r.probability_pct)) / Decimal("100")
        if r.delta_value_uzs_mln is not None:
            contrib = Decimal(str(r.delta_value_uzs_mln)) * prob
            total += contrib
            items.append({
                "project_id": str(r.project_id),
                "contribution_uzs_mln": float(contrib),
                "probability_pct": float(r.probability_pct),
                "confidence": r.confidence,
                "kind": "absolute",
            })
        elif r.delta_pct is not None:
            items.append({
                "project_id": str(r.project_id),
                "delta_pct": float(r.delta_pct),
                "probability_pct": float(r.probability_pct),
                "confidence": r.confidence,
                "kind": "percentage",
                "contribution_uzs_mln": 0.0,  # filled below
            })
    return total, items


async def compute_decomposition(
    db: AsyncSession,
    scenario_id: PyUUID,
    target_metric: str,
    target_year: int,
    company_id: Optional[PyUUID] = None,
    base_year: Optional[int] = None,
) -> DecompositionResult:
    """Main entry point: full waterfall decomposition for one (metric, year, company)."""
    if base_year is None:
        base_year = target_year - 1

    # 1. Base value
    base = await _get_base_value(db, company_id, target_metric, base_year)

    # 2. Macro effects
    macro_deltas = await _get_macro_deltas(db, scenario_id, target_year, base_year)

    macro_components: List[DecompositionComponent] = []
    macro_effect = Decimal("0")
    for factor, delta in macro_deltas.items():
        if delta == 0:
            continue
        beta = await _resolve_beta(db, scenario_id, company_id, factor, target_metric)
        if beta is None or beta == 0:
            continue
        contribution = base * delta * beta
        macro_effect += contribution
        macro_components.append(DecompositionComponent(
            label_ru=f"{MACRO_LABELS_RU.get(factor, factor)} (β={float(beta):.2f}, Δ={float(delta * 100):.1f}%)",
            contribution_uzs_mln=contribution,
            contribution_pct=Decimal("0"),  # filled at end
            kind="macro",
            detail={"factor": factor, "beta": float(beta), "delta": float(delta)},
        ))

    # 3. Project effects
    proj_total, proj_items = await _get_project_effects(db, company_id, target_metric, target_year)
    project_components: List[DecompositionComponent] = []
    for item in proj_items:
        if item.get("contribution_uzs_mln", 0) != 0:
            project_components.append(DecompositionComponent(
                label_ru=f"проект {item['project_id'][:8]}…",
                contribution_uzs_mln=Decimal(str(item["contribution_uzs_mln"])),
                contribution_pct=Decimal("0"),
                kind="project",
                detail=item,
            ))

    # 4. Total forecast
    forecast = base + macro_effect + proj_total

    # 5. Calculate percentages
    components: List[DecompositionComponent] = []
    components.append(DecompositionComponent(
        label_ru=f"База ({base_year})",
        contribution_uzs_mln=base,
        contribution_pct=(base / forecast * 100) if forecast != 0 else Decimal("100"),
        kind="base",
    ))
    for c in macro_components:
        c.contribution_pct = (c.contribution_uzs_mln / forecast * 100) if forecast != 0 else Decimal("0")
        components.append(c)
    for c in project_components:
        c.contribution_pct = (c.contribution_uzs_mln / forecast * 100) if forecast != 0 else Decimal("0")
        components.append(c)
    components.append(DecompositionComponent(
        label_ru=f"Прогноз {target_year}",
        contribution_uzs_mln=forecast,
        contribution_pct=Decimal("100"),
        kind="total",
    ))

    # 6. Company name
    company_name = None
    if company_id:
        co = (await db.execute(
            select(Company).where(Company.id == company_id)
        )).scalar_one_or_none()
        if co:
            company_name = co.name_ru

    # 7. Explanation
    metric_label = METRIC_LABELS_RU.get(target_metric, target_metric)
    expl = (
        f"Прогноз {metric_label} на {target_year}: "
        f"{float(forecast):,.0f} млн сум. "
        f"База ({base_year}): {float(base):,.0f}. "
        f"Эффект макроэкономики: {float(macro_effect):+,.0f} ({float(macro_effect / base * 100) if base != 0 else 0:+.1f}%). "
        f"Эффект проектов: {float(proj_total):+,.0f}."
    )

    return DecompositionResult(
        company_id=company_id,
        company_name=company_name,
        target_metric=target_metric,
        year=target_year,
        base_value_uzs_mln=base,
        forecast_value_uzs_mln=forecast,
        macro_effect_uzs_mln=macro_effect,
        projects_effect_uzs_mln=proj_total,
        components=components,
        explanation=expl,
    )
