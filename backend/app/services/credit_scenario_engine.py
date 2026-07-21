"""
Credit scenario engine — Pack 7.41.

Main service that:
  • Aggregates cp_loans with optional lender_type scope filter
  • Joins to financials for debt ratios (Debt/EBITDA, ICR, FCF/DS)
  • Applies scenario assumptions (forgiveness, refinance, default, accel)
  • Computes Expected Loss per loan (default Basel formula or custom)
  • Aggregates repayment schedule by year/quarter

The lender_type scope toggle is the central UX:
  "all_uz"   = state + local (default)
  "state"    = lender_type='state'
  "local"    = lender_type='local'
  "foreign"  = lender_type='foreign'
  "all"      = no filter (all 367 loans)
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.credit import CreditPortfolioLoan
from app.models.credit_scenario import (
    CreditPortfolioLoanScenario,
    CreditPortfolioScenario,
)
from app.models.loan_repayments import LoanRepayment
from app.services.risk_formula_evaluator import (
    compute_default_el,
    evaluate_formula,
)

# ============================================================================
# Scope filtering
# ============================================================================
SCOPE_FILTERS: dict[str, Optional[list[str]]] = {
    "all_uz": ["state", "local"],
    "state": ["state"],
    "local": ["local"],
    "foreign": ["foreign"],
    "bond": ["bond"],
    "all": None,
}


def scope_to_filter_clause(scope: str):
    """Returns a SQLAlchemy clause for filtering cp_loans by scope.

    Returns None if scope='all' (no filter).
    """
    types = SCOPE_FILTERS.get(scope, ["state", "local"])
    if types is None:
        return None
    return CreditPortfolioLoan.lender_type.in_(types)


# ============================================================================
# State summary (KPI strip)
# ============================================================================
async def compute_state_summary(
    db: AsyncSession,
    scope: str = "all_uz",
    scenario_id: Optional[UUID] = None,
) -> dict[str, Any]:
    """Compute KPI strip for the admin credit-nagruzka section."""
    base_filters = [CreditPortfolioLoan.deleted_at.is_(None)]
    scope_clause = scope_to_filter_clause(scope)
    if scope_clause is not None:
        base_filters.append(scope_clause)

    # Aggregate query
    agg_q = select(
        func.count(CreditPortfolioLoan.id).label("loans_count"),
        func.count(func.distinct(CreditPortfolioLoan.company_id)).label(
            "companies_count"
        ),
        func.count(func.distinct(CreditPortfolioLoan.bank)).label("banks_count"),
        func.coalesce(func.sum(CreditPortfolioLoan.sum_total), 0).label("sum_total"),
        func.coalesce(func.sum(CreditPortfolioLoan.debt_usd), 0).label("debt"),
        func.coalesce(
            func.sum(
                CreditPortfolioLoan.sum_total - func.coalesce(CreditPortfolioLoan.debt_usd, 0)
            ),
            0,
        ).label("repaid"),
        func.coalesce(
            func.sum(
                CreditPortfolioLoan.debt_usd
            ).filter(CreditPortfolioLoan.is_guaranteed.is_(True)),
            0,
        ).label("guaranteed"),
        func.coalesce(
            func.sum(
                CreditPortfolioLoan.debt_usd * CreditPortfolioLoan.rate
            ),
            0,
        ).label("rate_weighted_sum"),
        func.coalesce(
            func.sum(
                CreditPortfolioLoan.debt_usd
            ).filter(CreditPortfolioLoan.currency != "UZS"),
            0,
        ).label("fx_debt"),
    ).where(and_(*base_filters))

    res = await db.execute(agg_q)
    row = res.first()

    sum_total = Decimal(str(row.sum_total or 0))
    debt = Decimal(str(row.debt or 0))
    repaid = sum_total - debt
    guaranteed = Decimal(str(row.guaranteed or 0))

    repaid_pct = (repaid / sum_total * 100) if sum_total > 0 else Decimal(0)
    guaranteed_pct = (guaranteed / debt * 100) if debt > 0 else Decimal(0)
    avg_rate = (
        Decimal(str(row.rate_weighted_sum or 0)) / debt * 100
        if debt > 0
        else Decimal(0)
    )
    fx_pct = (Decimal(str(row.fx_debt or 0)) / debt * 100) if debt > 0 else Decimal(0)

    # Overdue: lookup from loan_repayments
    overdue_q = select(
        func.coalesce(func.sum(LoanRepayment.scheduled_amount_usd), 0).label("amt"),
        func.count(func.distinct(LoanRepayment.loan_id)).label("cnt"),
    ).where(LoanRepayment.status == "overdue")
    if scope_clause is not None:
        overdue_q = overdue_q.join(
            CreditPortfolioLoan, CreditPortfolioLoan.id == LoanRepayment.loan_id
        ).where(scope_clause)
    overdue_row = (await db.execute(overdue_q)).first()
    overdue_amt = Decimal(str(overdue_row.amt or 0))
    overdue_cnt = int(overdue_row.cnt or 0)

    # Next 12mo payments: rows where (period_year, period_quarter) <= +4 quarters
    today = date.today()
    plus_year = today + timedelta(days=365)
    n12_q = select(
        func.coalesce(func.sum(LoanRepayment.scheduled_amount_usd), 0).label("amt"),
    ).where(
        LoanRepayment.status.in_(("scheduled", "overdue")),
        # crude: any quarter ending within +365 days
        or_(
            LoanRepayment.period_year < plus_year.year,
            and_(
                LoanRepayment.period_year == plus_year.year,
                LoanRepayment.period_quarter
                <= ((plus_year.month - 1) // 3 + 1),
            ),
        ),
        or_(
            LoanRepayment.period_year > today.year,
            and_(
                LoanRepayment.period_year == today.year,
                LoanRepayment.period_quarter >= ((today.month - 1) // 3 + 1),
            ),
        ),
    )
    if scope_clause is not None:
        n12_q = n12_q.join(
            CreditPortfolioLoan, CreditPortfolioLoan.id == LoanRepayment.loan_id
        ).where(scope_clause)
    n12_row = (await db.execute(n12_q)).first()
    next_12mo = Decimal(str(n12_row.amt or 0))

    # Expected Loss aggregate
    el_total, flagged_count = await compute_el_aggregate(db, scope, scenario_id)

    return {
        "scope": scope,
        "loans_count": int(row.loans_count or 0),
        "companies_count": int(row.companies_count or 0),
        "banks_count": int(row.banks_count or 0),
        "sum_total_usd": sum_total.quantize(Decimal("0.01")),
        "debt_outstanding_usd": debt.quantize(Decimal("0.01")),
        "repaid_usd": repaid.quantize(Decimal("0.01")),
        "repaid_pct": repaid_pct.quantize(Decimal("0.01")),
        "guaranteed_usd": guaranteed.quantize(Decimal("0.01")),
        "guaranteed_pct": guaranteed_pct.quantize(Decimal("0.01")),
        "avg_rate_pct": avg_rate.quantize(Decimal("0.01")),
        "fx_exposure_pct": fx_pct.quantize(Decimal("0.01")),
        "overdue_usd": overdue_amt.quantize(Decimal("0.01")),
        "overdue_count": overdue_cnt,
        "expected_loss_usd": el_total,
        "flagged_loans_count": flagged_count,
        "next_12mo_payments_usd": next_12mo.quantize(Decimal("0.01")),
    }


# ============================================================================
# Expected Loss (Basel or custom)
# ============================================================================
async def compute_el_aggregate(
    db: AsyncSession,
    scope: str = "all_uz",
    scenario_id: Optional[UUID] = None,
) -> tuple[Decimal, int]:
    """Sum EL across all loans matching scope. Returns (total_el, flagged_count)."""
    # Load scenario (or use defaults)
    scenario = None
    formula_text = None
    rr_overrides = None
    if scenario_id:
        sres = await db.execute(
            select(CreditPortfolioScenario).where(
                CreditPortfolioScenario.id == scenario_id
            )
        )
        scenario = sres.scalar_one_or_none()
        if scenario:
            formula_text = scenario.risk_formula_text
            rr_overrides = dict(scenario.risk_rr_by_lender or {})

    scenario_default_rate = (
        Decimal(str(scenario.default_rate_pct))
        if scenario and scenario.default_rate_pct is not None
        else Decimal("0.02")
    )

    # Per-loan overrides
    overrides_by_loan: dict[UUID, CreditPortfolioLoanScenario] = {}
    if scenario_id:
        ovres = await db.execute(
            select(CreditPortfolioLoanScenario).where(
                CreditPortfolioLoanScenario.scenario_id == scenario_id
            )
        )
        for ov in ovres.scalars().all():
            overrides_by_loan[ov.loan_id] = ov

    # Iterate loans in scope
    base_filters = [CreditPortfolioLoan.deleted_at.is_(None)]
    scope_clause = scope_to_filter_clause(scope)
    if scope_clause is not None:
        base_filters.append(scope_clause)

    lres = await db.execute(
        select(CreditPortfolioLoan).where(and_(*base_filters))
    )
    loans = lres.scalars().all()

    total_el = Decimal(0)
    flagged_count = 0
    today = date.today()

    for loan in loans:
        debt = Decimal(str(loan.debt_usd or 0))
        if debt <= 0:
            continue

        # Просрочка по СРОКУ (maturity-proxy, как в credit_portfolio_helpers /
        # risk_metrics / credit_scenario.service): заём с наступившим сроком
        # погашения и остатком долга просрочен на (сегодня - date_due) дней. True
        # per-payment DPD в данных не captured — это консервативный прокси, чтобы
        # EL не обнулял делинквентность молча (>90д → +20% PD в формуле).
        overdue_days = (
            (today - loan.date_due).days
            if (loan.date_due and loan.date_due < today)
            else 0
        )
        days_to_maturity = (
            (loan.date_due - today).days if loan.date_due else 9999
        )
        repayments_remaining = debt  # crude — use debt itself as remaining

        ov = overrides_by_loan.get(loan.id)
        loan_pd = (
            Decimal(str(ov.default_probability))
            if ov and ov.default_probability is not None
            else Decimal(0)
        )

        # Pick formula
        if formula_text and formula_text.strip():
            ns = {
                "debt_usd": float(debt),
                "sum_total": float(loan.sum_total or 0),
                "sum_disbursed": float(loan.sum_disbursed or 0),
                "rate": float(loan.rate or 0),
                "is_guaranteed": bool(loan.is_guaranteed),
                "lender_type": loan.lender_type or "",
                "currency": loan.currency or "",
                "overdue_days": overdue_days,
                "days_to_maturity": days_to_maturity,
                "repayments_remaining": float(repayments_remaining),
                "loan": {
                    "default_probability": float(loan_pd) if loan_pd else None,
                    "forgiveness_pct": float(ov.forgiveness_pct) if ov and ov.forgiveness_pct else None,
                },
                "scenario": {
                    "default_rate_pct": float(scenario_default_rate),
                    "state_forgiveness_pct": float(scenario.state_forgiveness_pct or 0) if scenario else 0,
                },
                "company": {},
                "custom": {},
            }
            ok, _err, val = evaluate_formula(formula_text, ns)
            if ok and val is not None:
                el = val
            else:
                el = Decimal(0)
        else:
            _pd, _rr, el = compute_default_el(
                debt_usd=debt,
                loan_default_probability=loan_pd,
                scenario_default_rate_pct=scenario_default_rate,
                overdue_days=overdue_days,
                days_to_maturity=days_to_maturity,
                repayments_remaining_usd=repayments_remaining,
                is_guaranteed=bool(loan.is_guaranteed),
                lender_type=loan.lender_type,
                rr_overrides=rr_overrides,
            )

        if el > 0:
            total_el += el
            # Flagged: EL > 5% of debt OR overdue OR days_to_maturity < 365 with large remainder
            if (
                float(el) > float(debt) * 0.05
                or overdue_days > 90
                or (
                    days_to_maturity < 365
                    and float(repayments_remaining) > float(debt) * 0.5
                )
            ):
                flagged_count += 1

    return total_el.quantize(Decimal("0.01")), flagged_count


# ============================================================================
# Debt ratios (Debt/EBITDA, Debt/Revenue, ICR, FCF/DS) for TOP-N companies
# ============================================================================
async def compute_debt_ratios(
    db: AsyncSession,
    scope: str = "all_uz",
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """Compute debt ratios per company, joined with financials.

    Returns list of dicts ready for the UI.
    """
    base_filters = [CreditPortfolioLoan.deleted_at.is_(None)]
    scope_clause = scope_to_filter_clause(scope)
    if scope_clause is not None:
        base_filters.append(scope_clause)

    # Aggregate debt per company within scope
    q = (
        select(
            CreditPortfolioLoan.company_id,
            func.coalesce(func.sum(CreditPortfolioLoan.debt_usd), 0).label("debt"),
        )
        .where(and_(*base_filters))
        .group_by(CreditPortfolioLoan.company_id)
        .order_by(func.coalesce(func.sum(CreditPortfolioLoan.debt_usd), 0).desc())
        .limit(top_n)
    )
    res = await db.execute(q)
    rows = res.all()

    # Get company names
    company_ids = [r.company_id for r in rows]
    if not company_ids:
        return []
    cres = await db.execute(
        select(Company).where(Company.id.in_(company_ids))
    )
    co_by_id = {c.id: c for c in cres.scalars().all()}

    # Get financials (best-effort — may not have EBITDA etc for all companies)
    # We try to import financial models lazily — if not present, return basic info.
    try:
        from app.models.financial import FinancialLine, FinancialReport  # type: ignore

        # Pull latest financial year per company
        fin_by_co: dict[UUID, dict[str, Decimal]] = {}
        # Best-effort: fetch financial reports for these companies
        fres = await db.execute(
            select(FinancialReport).where(FinancialReport.company_id.in_(company_ids))
        )
        reports = fres.scalars().all()
        # Group by company, take latest year
        latest_by_co: dict[UUID, FinancialReport] = {}
        for fr in reports:
            existing = latest_by_co.get(fr.company_id)
            if not existing or (fr.year or 0) > (existing.year or 0):
                latest_by_co[fr.company_id] = fr

        for co_id, fr in latest_by_co.items():
            # Pull lines for this report and find key metrics
            lres = await db.execute(
                select(FinancialLine).where(FinancialLine.report_id == fr.id)
            )
            lines = lres.scalars().all()
            metrics: dict[str, Decimal] = {}
            for line in lines:
                # Heuristic: name contains keyword
                name = (getattr(line, "name", "") or "").lower()
                value = Decimal(str(getattr(line, "value", 0) or 0))
                if "ebitda" in name and "ebitda" not in metrics:
                    metrics["ebitda"] = value
                elif "revenue" in name or "выруч" in name:
                    if "revenue" not in metrics:
                        metrics["revenue"] = value
                elif ("fcf" in name) or ("free cash" in name) or ("свобод" in name and "поток" in name):
                    if "fcf" not in metrics:
                        metrics["fcf"] = value
            fin_by_co[co_id] = metrics
    except ImportError:
        fin_by_co = {}

    result: list[dict[str, Any]] = []
    for r in rows:
        co_id = r.company_id
        co = co_by_id.get(co_id)
        co_name = (co.name_short or co.name_ru or co.code) if co else "—"
        debt = Decimal(str(r.debt or 0))
        fin = fin_by_co.get(co_id, {})
        ebitda = fin.get("ebitda")
        revenue = fin.get("revenue")
        fcf = fin.get("fcf")

        debt_to_ebitda = (debt / ebitda) if ebitda and ebitda > 0 else None
        debt_to_revenue = (debt / revenue) if revenue and revenue > 0 else None

        # Risk zone based on D/EBITDA
        if debt_to_ebitda is None:
            risk_zone = "gray"
        elif debt_to_ebitda < Decimal("2.5"):
            risk_zone = "green"
        elif debt_to_ebitda < Decimal("3.0"):
            risk_zone = "amber"
        else:
            risk_zone = "red"

        result.append(
            {
                "company_id": co_id,
                "company_name": co_name,
                "debt_usd": debt.quantize(Decimal("0.01")),
                "ebitda_usd": ebitda,
                "revenue_usd": revenue,
                "fcf_usd": fcf,
                "debt_service_usd": None,  # TODO: from loan_repayments
                "debt_to_ebitda": (
                    debt_to_ebitda.quantize(Decimal("0.01"))
                    if debt_to_ebitda is not None
                    else None
                ),
                "debt_to_revenue": (
                    debt_to_revenue.quantize(Decimal("0.01"))
                    if debt_to_revenue is not None
                    else None
                ),
                "icr": None,  # TODO: requires interest expense
                "fcf_debt_service": None,
                "risk_zone": risk_zone,
            }
        )
    return result


# ============================================================================
# Repayment forecast (next N years, quarterly)
# ============================================================================
async def compute_repayment_forecast(
    db: AsyncSession,
    scope: str = "all_uz",
    years_back: int = 2,
    years_forward: int = 5,
    scenario_id: Optional[UUID] = None,
) -> list[dict[str, Any]]:
    """Quarterly repayment forecast across all loans in scope.

    Returns list of (year, quarter) summaries with scheduled/paid/overdue/custom/forgiven.
    """
    base_year = date.today().year - years_back
    horizon_year = date.today().year + years_forward

    base_filters = [
        LoanRepayment.period_year >= base_year,
        LoanRepayment.period_year <= horizon_year,
    ]
    scope_clause = scope_to_filter_clause(scope)

    q = (
        select(
            LoanRepayment.period_year,
            LoanRepayment.period_quarter,
            func.coalesce(
                func.sum(LoanRepayment.scheduled_amount_usd), 0
            ).label("scheduled"),
            func.coalesce(
                func.sum(LoanRepayment.actual_paid_amount_usd).filter(
                    LoanRepayment.status == "paid"
                ),
                0,
            ).label("paid"),
            func.coalesce(
                func.sum(LoanRepayment.scheduled_amount_usd).filter(
                    LoanRepayment.status == "overdue"
                ),
                0,
            ).label("overdue"),
            func.coalesce(
                func.sum(LoanRepayment.scheduled_amount_usd).filter(
                    LoanRepayment.status == "forgiven"
                ),
                0,
            ).label("forgiven"),
            func.coalesce(
                func.sum(LoanRepayment.scheduled_amount_usd).filter(
                    LoanRepayment.is_custom_schedule.is_(True)
                ),
                0,
            ).label("custom"),
            func.bool_or(LoanRepayment.is_custom_schedule).label("has_custom"),
        )
        .where(and_(*base_filters))
        .group_by(LoanRepayment.period_year, LoanRepayment.period_quarter)
        .order_by(LoanRepayment.period_year, LoanRepayment.period_quarter)
    )
    if scope_clause is not None:
        q = q.join(
            CreditPortfolioLoan, CreditPortfolioLoan.id == LoanRepayment.loan_id
        ).where(scope_clause)

    res = await db.execute(q)
    rows = res.all()
    this_year = date.today().year
    return [
        {
            "period_year": int(r.period_year),
            "period_quarter": int(r.period_quarter),
            "scheduled_usd": Decimal(str(r.scheduled or 0)).quantize(Decimal("0.01")),
            "paid_usd": Decimal(str(r.paid or 0)).quantize(Decimal("0.01")),
            "overdue_usd": Decimal(str(r.overdue or 0)).quantize(Decimal("0.01")),
            "forgiven_usd": Decimal(str(r.forgiven or 0)).quantize(Decimal("0.01")),
            "custom_usd": Decimal(str(r.custom or 0)).quantize(Decimal("0.01")),
            "is_custom": bool(r.has_custom),
            "is_history": int(r.period_year) < this_year,
        }
        for r in rows
    ]


# ============================================================================
# Top loans
# ============================================================================
async def compute_top_loans(
    db: AsyncSession,
    scope: str = "all_uz",
    scenario_id: Optional[UUID] = None,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """TOP-N loans by debt_usd within scope, with scenario overrides loaded."""
    base_filters = [CreditPortfolioLoan.deleted_at.is_(None)]
    scope_clause = scope_to_filter_clause(scope)
    if scope_clause is not None:
        base_filters.append(scope_clause)

    q = (
        select(
            CreditPortfolioLoan,
            func.coalesce(
                Company.name_short, Company.name_ru, Company.code
            ).label("company_name"),
        )
        .join(Company, Company.id == CreditPortfolioLoan.company_id)
        .where(and_(*base_filters))
        .order_by(CreditPortfolioLoan.debt_usd.desc().nulls_last())
        .limit(top_n)
    )
    res = await db.execute(q)
    rows = res.all()

    # Get overrides if scenario specified
    overrides: dict[UUID, CreditPortfolioLoanScenario] = {}
    if scenario_id and rows:
        loan_ids = [r[0].id for r in rows]
        ovres = await db.execute(
            select(CreditPortfolioLoanScenario).where(
                CreditPortfolioLoanScenario.scenario_id == scenario_id,
                CreditPortfolioLoanScenario.loan_id.in_(loan_ids),
            )
        )
        overrides = {ov.loan_id: ov for ov in ovres.scalars().all()}

    result: list[dict[str, Any]] = []
    for loan, co_name in rows:
        ov = overrides.get(loan.id)
        result.append(
            {
                "loan_id": loan.id,
                "loan_code": loan.loan_code,
                "bank": loan.bank,
                "company_name": co_name or "—",
                "lender_type": loan.lender_type,
                "is_guaranteed": bool(loan.is_guaranteed),
                "debt_usd": Decimal(str(loan.debt_usd or 0)).quantize(Decimal("0.01")),
                "rate": Decimal(str(loan.rate)) if loan.rate is not None else None,
                "date_due": loan.date_due,
                "forgiveness_pct": ov.forgiveness_pct if ov else None,
                "rate_override": ov.rate_override if ov else None,
                "rescheduled_to": ov.rescheduled_to if ov else None,
                "default_probability": ov.default_probability if ov else None,
                "partial_repayment_pct": ov.partial_repayment_pct if ov else None,
                "notes": ov.notes if ov else None,
            }
        )
    return result
