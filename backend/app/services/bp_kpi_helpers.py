"""Business Plan + KPI compute helpers — Python port of monolith logic.

Functions mirror the JS helpers in index.html lines 35357–42700:
- _bpCompute        → bp_compute
- _bpComputeSummary → bp_compute_summary
- _bpFactFromNSBU   → bp_fact_from_nsbu
- _bpAttentionIssues→ bp_attention_issues
- _kpiComputeSummary→ kpi_compute_summary
- _kpiAttentionIssues→ kpi_attention_issues
- _kpiComputeCompletion → kpi_compute_completion
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bp_kpi import (
    BP_METRICS,
    BP_METRIC_KEYS,
    BP_PERIODS,
    BpRecord,
    KpiIndicator,
    KpiManager,
)
from app.models.company import Company

# Sector colors for fallback in dashboards (mirror monolith SECTOR_SOLID)
SECTOR_FALLBACK_COLORS = {
    "mining": "#9B8EC4",
    "metallurgy": "#9B8EC4",
    "mining_metallurgy": "#9B8EC4",
    "oil_gas": "#0A7B5E",
    "oilgas": "#0A7B5E",
    "energy": "#EF9F27",
    "transport": "#378ADD",
    "transport_communications": "#378ADD",
    "telecom": "#378ADD",
    "chemistry": "#888780",
    "other": "#888780",
}


def sector_color(co: Company) -> Optional[str]:
    if co.sector and co.sector.color_hex:
        return co.sector.color_hex
    if co.sector and co.sector.code:
        return SECTOR_FALLBACK_COLORS.get(co.sector.code, "#888780")
    return "#888780"


def sector_code(co: Company) -> Optional[str]:
    return co.sector.code if co.sector else None


# ─── BP: NSBU autofill ────────────────────────────────────────────

async def bp_fact_from_nsbu(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    metric: str,
) -> Optional[Decimal]:
    """Look up annual fact from financials_detailed (NSBU).

    Maps BP metric names to FinancialsDetailed columns. Returns None if
    not available. Only used for period='annual'.
    """
    # Load FinancialsDetailed lazily — module may not exist in some deployments
    try:
        from app.models.financial import FinancialsDetailed  # type: ignore
    except Exception:
        try:
            from app.models.financials_detailed import FinancialsDetailed  # type: ignore
        except Exception:
            return None

    # Map BP metric → financial field name (heuristic, mirror typical NSBU layout)
    metric_to_attr = {
        "revenue": ["revenue", "net_revenue", "total_revenue"],
        "cogs": ["cogs", "cost_of_sales"],
        "grossProfit": ["gross_profit"],
        "opExpenses": ["op_expenses", "period_expenses"],
        "sellExp": ["sell_exp", "selling_expenses"],
        "adminExp": ["admin_exp", "administrative_expenses"],
        "otherOpExp": ["other_op_exp"],
        "otherOpInc": ["other_op_inc"],
        "opProfit": ["op_profit", "operating_profit"],
        "finIncome": ["fin_income", "financial_income"],
        "divIncome": ["div_income", "dividend_income"],
        "intIncome": ["int_income", "interest_income"],
        "fxIncome": ["fx_income"],
        "otherFinInc": ["other_fin_inc"],
        "finCost": ["fin_cost", "financial_cost"],
        "intExp": ["int_exp", "interest_expense"],
        "fxLoss": ["fx_loss"],
        "otherFinExp": ["other_fin_exp"],
        "hhProfit": ["hh_profit"],
        "pbt": ["pbt", "profit_before_tax"],
        "tax": ["tax", "income_tax"],
        "profit": ["profit", "net_profit"],
    }
    attrs = metric_to_attr.get(metric, [])
    if not attrs:
        return None

    try:
        q = (
            select(FinancialsDetailed)
            .where(FinancialsDetailed.company_id == company_id)
            .where(FinancialsDetailed.year == year)
        )
        # If FinancialsDetailed has a "source" column use only NSBU rows
        if hasattr(FinancialsDetailed, "source"):
            q = q.where(FinancialsDetailed.source.in_(["NSBU", "nsbu", "НСБУ"]))
        row = (await db.execute(q)).scalars().first()
        if row is None:
            return None
        for a in attrs:
            if hasattr(row, a):
                v = getattr(row, a)
                if v is not None:
                    return Decimal(str(v))
    except Exception:
        return None
    return None


# ─── BP compute (single company, year, period) ───────────────────

async def bp_compute(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    period: str,
    nsbu_fallback: bool = True,
) -> Dict[str, Dict]:
    """Mirror of monolith `_bpCompute(co, year, period)`.

    Returns dict of {metric_key: {plan, expect, fact, fact_auto}}.
    Auto-calculates derived metrics (grossProfit, opProfit, hhProfit, pbt, profit)
    from inputs when not explicitly stored. Auto-fills `fact` from NSBU only
    for period='annual'.
    """
    # Load all stored BP records
    rows = (
        await db.execute(
            select(BpRecord)
            .where(BpRecord.company_id == company_id)
            .where(BpRecord.year == year)
            .where(BpRecord.period == period)
        )
    ).scalars().all()

    stored: Dict[str, Dict] = {r.metric: {"plan": r.plan, "expect": r.expect, "fact": r.fact} for r in rows}

    out: Dict[str, Dict] = {}
    for k in BP_METRIC_KEYS:
        cell = stored.get(k, {"plan": None, "expect": None, "fact": None})
        out[k] = {
            "plan": cell.get("plan"),
            "expect": cell.get("expect"),
            "fact": cell.get("fact"),
            "fact_auto": False,
        }

    # Auto-calc derived metrics for each column (plan/expect/fact)
    def _v(metric: str, col: str):
        return out[metric][col] if out[metric][col] is not None else None

    for col in ("plan", "expect", "fact"):
        rev = _v("revenue", col)
        cogs = _v("cogs", col)
        if rev is not None and cogs is not None and out["grossProfit"][col] is None:
            out["grossProfit"][col] = (Decimal(rev) - abs(Decimal(cogs))).quantize(Decimal("0.001"))

        gp = out["grossProfit"][col]
        opex = _v("opExpenses", col)
        other_inc = _v("otherOpInc", col)
        if gp is not None and opex is not None and out["opProfit"][col] is None:
            out["opProfit"][col] = (
                Decimal(gp) - abs(Decimal(opex)) + (Decimal(other_inc) if other_inc is not None else Decimal(0))
            ).quantize(Decimal("0.001"))

        op = out["opProfit"][col]
        fi = _v("finIncome", col)
        fc = _v("finCost", col)
        if op is not None and out["hhProfit"][col] is None:
            out["hhProfit"][col] = (
                Decimal(op)
                + (Decimal(fi) if fi is not None else Decimal(0))
                - (abs(Decimal(fc)) if fc is not None else Decimal(0))
            ).quantize(Decimal("0.001"))

        if out["hhProfit"][col] is not None and out["pbt"][col] is None:
            out["pbt"][col] = out["hhProfit"][col]

        pbt = out["pbt"][col]
        tax = _v("tax", col)
        if pbt is not None and tax is not None and out["profit"][col] is None:
            out["profit"][col] = (Decimal(pbt) - abs(Decimal(tax))).quantize(Decimal("0.001"))

    # NSBU autofill — only for annual
    if nsbu_fallback and period == "annual":
        for k in BP_METRIC_KEYS:
            if out[k]["fact"] is None:
                v = await bp_fact_from_nsbu(db, company_id, year, k)
                if v is not None:
                    out[k]["fact"] = v
                    out[k]["fact_auto"] = True

    return out


# ─── BP attention issues ──────────────────────────────────────────

def bp_pct(fact: Optional[Decimal], plan: Optional[Decimal]) -> Optional[float]:
    if plan is None or plan == 0 or fact is None:
        return None
    return float(fact) / float(plan)


def bp_fmt(v: Optional[Decimal]) -> str:
    if v is None:
        return "—"
    av = abs(float(v))
    if av >= 1000:
        return f"{round(float(v)):,}".replace(",", " ")
    if av >= 10:
        return f"{float(v):.0f}"
    return f"{float(v):.2f}"


async def bp_attention_issues(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    period: str,
) -> List[Dict]:
    """Mirror of monolith `_bpAttentionIssues`.

    Returns up to 5 issues sorted by severity. Skips KPI-side issues which
    are returned by kpi_attention_issues separately.
    """
    issues: List[Dict] = []
    comp = await bp_compute(db, company_id, year, period)

    # Rule 1: deviation ≥15% below plan on key metrics
    label_by_key = {m["key"]: m["label"] for m in BP_METRICS}
    for k in ("revenue", "opProfit", "profit"):
        c = comp[k]
        if c["plan"] is not None and c["fact"] is not None and c["plan"] != 0:
            ratio = float(c["fact"]) / float(c["plan"])
            if ratio < 0.85:
                issues.append({
                    "severity": "high" if ratio < 0.70 else "medium",
                    "title": label_by_key[k],
                    "value": f"{round(ratio * 100)}% плана",
                    "detail": f"Факт {bp_fmt(c['fact'])} vs план {bp_fmt(c['plan'])}",
                })

    # Rule 2: cost ratio increase
    if (
        comp["cogs"]["fact"] is not None and comp["revenue"]["fact"] is not None
        and comp["revenue"]["fact"] != 0
    ):
        cost_ratio = abs(float(comp["cogs"]["fact"])) / float(comp["revenue"]["fact"])
        if (
            comp["cogs"]["plan"] is not None and comp["revenue"]["plan"] is not None
            and comp["revenue"]["plan"] != 0
        ):
            cost_ratio_plan = abs(float(comp["cogs"]["plan"])) / float(comp["revenue"]["plan"])
            if cost_ratio > cost_ratio_plan * 1.10:
                issues.append({
                    "severity": "medium",
                    "title": "Рост доли себестоимости",
                    "value": f"{round(cost_ratio * 100)}% vs план {round(cost_ratio_plan * 100)}%",
                    "detail": "Давление на маржинальность",
                })

    sev_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: sev_order.get(x["severity"], 9))
    return issues[:5]


# ─── KPI compute ──────────────────────────────────────────────────

def kpi_compute_completion(ind: KpiIndicator, period: str) -> Optional[float]:
    """Compute fact/plan ratio for an indicator at a given period.

    period: 'year' | 'q1'..'q4'.

    Fix 2026-05-23: для period='year', если annual fact_year/plan_year не
    введены, делаем YTD-fallback — складываем кварталы где есть и план, и
    факт. Иначе год показывал ~0% так как fact_year заведён у <1% индикаторов
    (юзеры закрывают факт поквартально, годовой подбивается в декабре).
    """
    if period == "year":
        plan = ind.plan_year
        fact = ind.fact_year
        if plan is not None and plan != 0 and fact is not None:
            return float(fact) / float(plan)
        # YTD fallback: суммируем кварталы со полной парой plan+fact.
        sum_p, sum_f = 0.0, 0.0
        had_pair = False
        for q in ("q1", "q2", "q3", "q4"):
            qp = getattr(ind, f"{q}_plan", None)
            qf = getattr(ind, f"{q}_fact", None)
            if qp is not None and qf is not None and float(qp) != 0:
                sum_p += float(qp)
                sum_f += float(qf)
                had_pair = True
        if had_pair and sum_p != 0:
            return sum_f / sum_p
        return None
    else:
        plan = getattr(ind, f"{period}_plan", None)
        fact = getattr(ind, f"{period}_fact", None)
        if plan is None or plan == 0 or fact is None:
            return None
        return float(fact) / float(plan)


def kpi_status_for_pct(pct: float) -> str:
    if pct >= 100:
        return "over"
    if pct >= 95:
        return "hit"
    if pct >= 75:
        return "risk"
    if pct >= 50:
        return "crit"
    return "fail"


async def kpi_attention_issues(
    db: AsyncSession,
    company_id: UUID,
    year: int,
    period: str,
) -> List[Dict]:
    """Mirror of monolith `_kpiAttentionIssues`."""
    period_key = "year" if period == "annual" else period
    rows = (
        await db.execute(
            select(KpiManager)
            .where(KpiManager.company_id == company_id)
            .where(KpiManager.year == year)
            .options(selectinload(KpiManager.indicators))
            .order_by(KpiManager.sort_order)
        )
    ).scalars().all()

    issues: List[Dict] = []
    for mgr in rows:
        for ind in mgr.indicators:
            ratio = kpi_compute_completion(ind, period_key)
            if ratio is None:
                continue
            if period_key == "year":
                w = float(ind.weight or 0)
            else:
                w = float(getattr(ind, f"{period_key}_weight", 0) or 0)
            if w < 5:
                continue
            pct = ratio * 100
            if pct < 75:
                short = (mgr.short_title or mgr.title or "")[:30]
                issues.append({
                    "severity": "high" if pct < 50 else "medium",
                    "title": (ind.name or "")[:60],
                    "value": f"{round(pct)}% (вес {round(w)})",
                    "detail": f"{short}",
                })

    sev = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: sev.get(x["severity"], 9))
    return issues[:3]
