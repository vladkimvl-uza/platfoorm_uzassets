"""
Credit scenarios route — Pack 7.41.

Endpoints (mounted at /api/credit-scenario):
  GET    /scenarios                          — list all credit scenarios
  GET    /scenarios/{id}                     — get one
  POST   /scenarios                          — create (admin)
  PUT    /scenarios/{id}                     — update assumptions (admin)
  DELETE /scenarios/{id}                     — delete (admin)

  GET    /state-summary                      — KPI strip (scope-aware)
  GET    /debt-ratios                        — TOP-N companies with ratios
  GET    /repayment-forecast                 — quarterly forecast
  GET    /top-loans                          — TOP-N loans with overrides

  GET    /loan-overrides/{scenario_id}       — list overrides for a scenario
  PUT    /loan-overrides/{scenario_id}/{loan_id}  — upsert one override (admin)
  DELETE /loan-overrides/{scenario_id}/{loan_id}  — remove override (admin)

  GET    /custom-indicators                  — list all
  POST   /custom-indicators                  — create (admin)
  PUT    /custom-indicators/{id}             — update (admin)
  DELETE /custom-indicators/{id}             — delete (admin)

  POST   /formula/validate                   — validate formula syntax
  POST   /formula/test                       — test formula on one loan
  GET    /formula/default                    — get default Basel formula text

  GET    /default-rr-by-lender               — get default recovery rates
"""
from __future__ import annotations

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.credit import CreditPortfolioLoan
from app.models.credit_scenario import (
    CreditPortfolioScenario,
    CreditPortfolioLoanScenario,
    CreditCustomIndicator,
    CUSTOM_INDICATOR_INPUT_TYPES,
    CUSTOM_INDICATOR_AGGREGATIONS,
)
from app.schemas.credit_scenario import (
    CreditPortfolioScenarioOut,
    CreditPortfolioScenarioCreate,
    CreditPortfolioScenarioUpdate,
    LoanScenarioOut,
    LoanScenarioCreate,
    LoanScenarioUpdate,
    CustomIndicatorOut,
    CustomIndicatorCreate,
    CustomIndicatorUpdate,
    StateSummary,
    DebtRatioRow,
    RepaymentQuarterRow,
    TopLoanRow,
    FormulaValidateRequest,
    FormulaValidateResponse,
    FormulaTestRequest,
    FormulaTestResponse,
)
from app.services.credit_scenario_engine import (
    compute_state_summary,
    compute_debt_ratios,
    compute_repayment_forecast,
    compute_top_loans,
)
from app.services.risk_formula_evaluator import (
    validate_formula,
    evaluate_formula,
    DEFAULT_FORMULA_TEXT,
    DEFAULT_RR_BY_LENDER,
)


router = APIRouter(prefix="/credit-scenario", tags=["credit-scenario"])


# Admin-only guard
def _admin_only(user: User):
    """Pack 7.41 — admin check matches Vladimir's existing pattern: email-based.

    Adjust the comparison list to your actual admin emails.
    """
    email = (getattr(user, "email", "") or "").lower()
    if email not in {"v.kim@uz-assets.uz"}:
        raise HTTPException(status_code=403, detail="Admin access required")


# ============================================================================
# Scenarios CRUD
# ============================================================================
@router.get("/scenarios", response_model=List[CreditPortfolioScenarioOut])
async def list_scenarios(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    res = await db.execute(
        select(CreditPortfolioScenario).order_by(
            CreditPortfolioScenario.created_at.asc()
        )
    )
    return list(res.scalars().all())


@router.get("/scenarios/{scenario_id}", response_model=CreditPortfolioScenarioOut)
async def get_scenario(
    scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    res = await db.execute(
        select(CreditPortfolioScenario).where(
            CreditPortfolioScenario.id == scenario_id
        )
    )
    sc = res.scalar_one_or_none()
    if not sc:
        raise HTTPException(404, "Scenario not found")
    return sc


@router.post("/scenarios", response_model=CreditPortfolioScenarioOut, status_code=201)
async def create_scenario(
    body: CreditPortfolioScenarioCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    # Check uniqueness of macro_scenario_key
    existing = await db.execute(
        select(CreditPortfolioScenario.id).where(
            CreditPortfolioScenario.macro_scenario_key == body.macro_scenario_key
        )
    )
    if existing.first():
        raise HTTPException(
            400, f"Scenario with key '{body.macro_scenario_key}' already exists"
        )

    sc = CreditPortfolioScenario(
        **body.model_dump(),
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(sc)
    await db.commit()
    await db.refresh(sc)
    return sc


@router.put("/scenarios/{scenario_id}", response_model=CreditPortfolioScenarioOut)
async def update_scenario(
    scenario_id: UUID,
    body: CreditPortfolioScenarioUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    res = await db.execute(
        select(CreditPortfolioScenario).where(
            CreditPortfolioScenario.id == scenario_id
        )
    )
    sc = res.scalar_one_or_none()
    if not sc:
        raise HTTPException(404, "Scenario not found")

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(sc, k, v)
    sc.updated_by_user_id = user.id
    await db.commit()
    await db.refresh(sc)
    return sc


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    res = await db.execute(
        select(CreditPortfolioScenario).where(
            CreditPortfolioScenario.id == scenario_id
        )
    )
    sc = res.scalar_one_or_none()
    if not sc:
        raise HTTPException(404, "Scenario not found")
    await db.delete(sc)
    await db.commit()
    return None


# ============================================================================
# Computed views
# ============================================================================
@router.get("/state-summary", response_model=StateSummary)
async def state_summary(
    scope: str = Query("all_uz"),
    scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """KPI strip — scope-aware credit aggregates."""
    data = await compute_state_summary(db, scope=scope, scenario_id=scenario_id)
    return data


@router.get("/debt-ratios", response_model=List[DebtRatioRow])
async def debt_ratios(
    scope: str = Query("all_uz"),
    top_n: int = Query(10, ge=1, le=22),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = await compute_debt_ratios(db, scope=scope, top_n=top_n)
    return data


@router.get("/repayment-forecast", response_model=List[RepaymentQuarterRow])
async def repayment_forecast(
    scope: str = Query("all_uz"),
    years_back: int = Query(2, ge=0, le=10),
    years_forward: int = Query(5, ge=1, le=15),
    scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await compute_repayment_forecast(
        db,
        scope=scope,
        years_back=years_back,
        years_forward=years_forward,
        scenario_id=scenario_id,
    )


@router.get("/top-loans", response_model=List[TopLoanRow])
async def top_loans(
    scope: str = Query("all_uz"),
    top_n: int = Query(10, ge=1, le=50),
    scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await compute_top_loans(
        db, scope=scope, top_n=top_n, scenario_id=scenario_id
    )


# ============================================================================
# Per-loan overrides
# ============================================================================
@router.get(
    "/loan-overrides/{scenario_id}", response_model=List[LoanScenarioOut]
)
async def list_loan_overrides(
    scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    res = await db.execute(
        select(CreditPortfolioLoanScenario).where(
            CreditPortfolioLoanScenario.scenario_id == scenario_id
        )
    )
    return list(res.scalars().all())


@router.put(
    "/loan-overrides/{scenario_id}/{loan_id}", response_model=LoanScenarioOut
)
async def upsert_loan_override(
    scenario_id: UUID,
    loan_id: UUID,
    body: LoanScenarioUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    res = await db.execute(
        select(CreditPortfolioLoanScenario).where(
            and_(
                CreditPortfolioLoanScenario.scenario_id == scenario_id,
                CreditPortfolioLoanScenario.loan_id == loan_id,
            )
        )
    )
    ov = res.scalar_one_or_none()
    if ov is None:
        # Create new
        ov = CreditPortfolioLoanScenario(
            scenario_id=scenario_id,
            loan_id=loan_id,
            **body.model_dump(exclude_unset=True),
        )
        db.add(ov)
    else:
        for k, v in body.model_dump(exclude_unset=True).items():
            setattr(ov, k, v)
    await db.commit()
    await db.refresh(ov)
    return ov


@router.delete(
    "/loan-overrides/{scenario_id}/{loan_id}", status_code=204
)
async def delete_loan_override(
    scenario_id: UUID,
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    res = await db.execute(
        select(CreditPortfolioLoanScenario).where(
            and_(
                CreditPortfolioLoanScenario.scenario_id == scenario_id,
                CreditPortfolioLoanScenario.loan_id == loan_id,
            )
        )
    )
    ov = res.scalar_one_or_none()
    if ov is None:
        raise HTTPException(404, "Override not found")
    await db.delete(ov)
    await db.commit()
    return None


# ============================================================================
# Custom indicators
# ============================================================================
@router.get("/custom-indicators", response_model=List[CustomIndicatorOut])
async def list_custom_indicators(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    res = await db.execute(
        select(CreditCustomIndicator).order_by(CreditCustomIndicator.created_at.asc())
    )
    return list(res.scalars().all())


@router.post(
    "/custom-indicators", response_model=CustomIndicatorOut, status_code=201
)
async def create_custom_indicator(
    body: CustomIndicatorCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    if body.input_type not in CUSTOM_INDICATOR_INPUT_TYPES:
        raise HTTPException(
            400,
            f"input_type must be one of: {', '.join(CUSTOM_INDICATOR_INPUT_TYPES)}",
        )
    if (
        body.aggregation is not None
        and body.aggregation not in CUSTOM_INDICATOR_AGGREGATIONS
    ):
        raise HTTPException(
            400,
            f"aggregation must be one of: {', '.join(CUSTOM_INDICATOR_AGGREGATIONS)}",
        )
    # Check key uniqueness
    existing = await db.execute(
        select(CreditCustomIndicator.id).where(CreditCustomIndicator.key == body.key)
    )
    if existing.first():
        raise HTTPException(400, f"Indicator with key '{body.key}' already exists")

    ind = CreditCustomIndicator(
        **body.model_dump(),
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db.add(ind)
    await db.commit()
    await db.refresh(ind)
    return ind


@router.put(
    "/custom-indicators/{indicator_id}", response_model=CustomIndicatorOut
)
async def update_custom_indicator(
    indicator_id: UUID,
    body: CustomIndicatorUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    res = await db.execute(
        select(CreditCustomIndicator).where(CreditCustomIndicator.id == indicator_id)
    )
    ind = res.scalar_one_or_none()
    if not ind:
        raise HTTPException(404, "Indicator not found")

    data = body.model_dump(exclude_unset=True)
    if "input_type" in data and data["input_type"] not in CUSTOM_INDICATOR_INPUT_TYPES:
        raise HTTPException(
            400,
            f"input_type must be one of: {', '.join(CUSTOM_INDICATOR_INPUT_TYPES)}",
        )
    if (
        "aggregation" in data
        and data["aggregation"] is not None
        and data["aggregation"] not in CUSTOM_INDICATOR_AGGREGATIONS
    ):
        raise HTTPException(
            400,
            f"aggregation must be one of: {', '.join(CUSTOM_INDICATOR_AGGREGATIONS)}",
        )

    for k, v in data.items():
        setattr(ind, k, v)
    ind.updated_by_user_id = user.id
    await db.commit()
    await db.refresh(ind)
    return ind


@router.delete("/custom-indicators/{indicator_id}", status_code=204)
async def delete_custom_indicator(
    indicator_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    res = await db.execute(
        select(CreditCustomIndicator).where(CreditCustomIndicator.id == indicator_id)
    )
    ind = res.scalar_one_or_none()
    if not ind:
        raise HTTPException(404, "Indicator not found")
    await db.delete(ind)
    await db.commit()
    return None


# ============================================================================
# Formula validation / test
# ============================================================================
@router.post("/formula/validate", response_model=FormulaValidateResponse)
async def formula_validate(
    body: FormulaValidateRequest,
    _user: User = Depends(get_current_user),
):
    ok, err, pos, vars_used = validate_formula(body.formula_text)
    return FormulaValidateResponse(
        ok=ok, error=err, error_position=pos, variables_used=vars_used
    )


@router.post("/formula/test", response_model=FormulaTestResponse)
async def formula_test(
    body: FormulaTestRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    # Pick a sample loan
    if body.loan_id:
        res = await db.execute(
            select(CreditPortfolioLoan).where(CreditPortfolioLoan.id == body.loan_id)
        )
    else:
        res = await db.execute(
            select(CreditPortfolioLoan)
            .where(
                CreditPortfolioLoan.deleted_at.is_(None),
                CreditPortfolioLoan.debt_usd.isnot(None),
            )
            .limit(1)
        )
    loan = res.scalar_one_or_none()
    if loan is None:
        return FormulaTestResponse(ok=False, error="Нет ни одного кредита для теста")

    from datetime import date as _date
    today = _date.today()
    days_to_maturity = (loan.date_due - today).days if loan.date_due else 9999

    ns = {
        "debt_usd": float(loan.debt_usd or 0),
        "sum_total": float(loan.sum_total or 0),
        "sum_disbursed": float(loan.sum_disbursed or 0),
        "rate": float(loan.rate or 0),
        "is_guaranteed": bool(loan.is_guaranteed),
        "lender_type": loan.lender_type or "",
        "currency": loan.currency or "",
        "overdue_days": 0,
        "days_to_maturity": days_to_maturity,
        "repayments_remaining": float(loan.debt_usd or 0),
        "loan": {
            "default_probability": None,
            "forgiveness_pct": None,
        },
        "scenario": {
            "default_rate_pct": 0.02,
            "state_forgiveness_pct": 0.0,
        },
        "company": {},
        "custom": {},
    }

    ok, err, val = evaluate_formula(body.formula_text, ns)

    steps = [
        f"debt_usd = {ns['debt_usd']}",
        f"lender_type = {ns['lender_type']}, is_guaranteed = {ns['is_guaranteed']}",
        f"days_to_maturity = {ns['days_to_maturity']}",
        f"scenario.default_rate_pct = {ns['scenario']['default_rate_pct']}",
    ]
    if ok:
        steps.append(f"=> EL = {val}")

    return FormulaTestResponse(
        ok=ok,
        error=err,
        loan_code=loan.loan_code,
        inputs=ns,
        steps=steps,
        final_value=val,
    )


@router.get("/formula/default")
async def formula_default(_user: User = Depends(get_current_user)):
    return {"formula_text": DEFAULT_FORMULA_TEXT}


@router.get("/default-rr-by-lender")
async def default_rr(_user: User = Depends(get_current_user)):
    return DEFAULT_RR_BY_LENDER


# ============================================================================
# Pack 7.41 — Executive Dashboard endpoints (overview + segmentation)
# ============================================================================

@router.get("/overview")
async def get_overview(
    cp_scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Executive dashboard overview — Pack 7.41 (Pack 7.44 fix).

    Uses _aggregate_impl from credit_portfolio.py as the source of truth,
    so numbers MATCH the /credit-portfolio page exactly.

    Adds extra fields needed by ExecDashCreditBlock:
      - by_maturity (segmentation by bucket)
      - expected_loss_usd / expected_loss_loans
      - by_currency includes debt_currency (native amount, not USD)
    """
    from datetime import date as _date
    from decimal import Decimal as Dec
    from collections import defaultdict
    from app.api.routes.credit_portfolio import _aggregate_impl
    from app.models.credit import CreditPortfolioLoan

    # Ensure tables exist (self-heal for migration)
    try:
        from app.core.runtime_migrations_p741 import pack_741_self_heal
        await pack_741_self_heal(db)
    except Exception:
        pass

    # === 1. Get authoritative aggregate from credit-portfolio source-of-truth ===
    aggr = await _aggregate_impl(
        company_id=None, company_code=None, as_of=None,
        db=db, user=user,
    )

    # === 2. Build by_maturity from raw loans (not in credit-portfolio response) ===
    today = _date.today()
    loans = (await db.execute(
        select(CreditPortfolioLoan).where(CreditPortfolioLoan.deleted_at.is_(None))
    )).scalars().all()

    MATURITY_LABELS = {
        "overdue": "просрочено", "lt_1y": "до 1 года",
        "1_3y": "от 1 до 3 лет", "3_5y": "от 3 до 5 лет", "gt_5y": "более 5 лет",
    }
    by_maturity = defaultdict(lambda: {"debt": 0.0, "count": 0})
    overdue_companies = set()
    due_12mo_loans = 0

    for ln in loans:
        debt = float(ln.debt_usd or 0)
        if ln.date_due:
            dtm = (ln.date_due - today).days
            if ln.date_due < today and debt > 0:
                bucket = "overdue"
                if ln.company_id:
                    overdue_companies.add(ln.company_id)
            elif dtm < 365:
                bucket = "lt_1y"
                due_12mo_loans += 1
            elif dtm < 365 * 3:
                bucket = "1_3y"
            elif dtm < 365 * 5:
                bucket = "3_5y"
            else:
                bucket = "gt_5y"
        else:
            bucket = "gt_5y"
        by_maturity[bucket]["debt"] += debt
        by_maturity[bucket]["count"] += 1

    outstanding = float(aggr.total_usd or 0)

    def _maturity_list():
        rows = []
        for k, v in by_maturity.items():
            pct = (v["debt"] / outstanding * 100) if outstanding > 0 else 0
            rows.append({
                "bucket": k, "label_ru": MATURITY_LABELS.get(k, k),
                "debt_usd": v["debt"], "loans_count": v["count"], "pct": pct,
            })
        rows.sort(key=lambda x: x["debt_usd"], reverse=True)
        return rows

    # === 3. Lender labels in Russian (matches credit.ts CP_LENDER_LABELS) ===
    LENDER_LABELS_RU = {
        "state": "государство", "local": "местные банки",
        "foreign": "иностранные", "bond": "облигации",
    }
    CURRENCY_LABELS_RU = {
        "USD": "доллар США", "UZS": "сум", "CNY": "юань", "EUR": "евро",
        "JPY": "иена", "RUB": "рубль", "SDR": "СДР", "KZT": "тенге", "GBP": "фунт",
    }

    by_lender = [
        {
            "lender_type": x.lender_type,
            "label_ru": LENDER_LABELS_RU.get(x.lender_type, x.label),
            "label": x.label,
            "color": x.color,
            "debt_usd": float(x.debt_usd or 0),
            "loans_count": int(x.loans_count or 0),
            "pct": float(x.pct_of_total or 0) * 100,
        }
        for x in aggr.by_lender_type
    ]

    by_currency = [
        {
            "currency": x.currency,
            "label_ru": CURRENCY_LABELS_RU.get(x.currency, x.currency),
            "debt_usd": float(x.debt_usd or 0),
            "debt_currency": float(x.debt_currency or 0),
            "loans_count": int(x.loans_count or 0),
            "pct": float(x.pct_of_total or 0) * 100,
            "avg_rate": float(x.avg_rate or 0) if x.avg_rate else None,
        }
        for x in aggr.by_currency
    ]

    # === 4. FX exposure (% non-UZS) — match credit-portfolio logic ===
    non_uzs = sum(float(x.debt_usd or 0) for x in aggr.by_currency if x.currency != "UZS")
    fx_exposure_pct = (non_uzs / outstanding * 100) if outstanding > 0 else 0

    # === 5. Expected Loss = Σ debt × PD × (1 − RR) — match Pack 7.41 default formula ===
    DEFAULT_RR_BY_LENDER = {"state": 0.6, "local": 0.5, "foreign": 0.45, "bond": 0.40}
    DEFAULT_PD_BY_LENDER = {"state": 0.015, "local": 0.035, "foreign": 0.020, "bond": 0.025}
    el_total = 0.0
    el_loans = 0
    for ln in loans:
        debt = float(ln.debt_usd or 0)
        if debt <= 0:
            continue
        rr = DEFAULT_RR_BY_LENDER.get(ln.lender_type, 0.5)
        if ln.is_guaranteed:
            rr = min(0.85, rr + 0.30)
        pd = DEFAULT_PD_BY_LENDER.get(ln.lender_type, 0.025)
        if ln.date_due and ln.date_due < today:
            pd = min(1.0, pd * 5)
        contribution = debt * pd * (1 - rr)
        el_total += contribution
        if contribution > 1000:
            el_loans += 1

    # === 6. Build response (compatible with old shape + additions) ===
    return {
        "portfolio_total_usd": float(aggr.loaned_total_usd or 0),
        "outstanding_usd": outstanding,
        "repaid_usd": float(aggr.repaid_total_usd or 0),
        "repaid_pct": float(aggr.repaid_pct or 0) * 100,
        "loans_count": int(aggr.loans_count or 0),
        "banks_count": int(aggr.banks_count or 0),
        "companies_count": len(set(ln.company_id for ln in loans if ln.company_id and (ln.debt_usd or 0) > 0)),
        "soes_count": 22,
        "avg_rate_weighted": float(aggr.avg_rate or 0) * 100,  # _aggregate_impl returns fraction (0.06), UI expects percent (6.0)
        "guaranteed_usd": float(aggr.guaranteed_amount or 0),
        "guaranteed_pct": (float(aggr.guaranteed_amount or 0) / outstanding * 100) if outstanding > 0 else 0,
        "due_12mo_usd": float(aggr.payment_this_year or 0) + float(aggr.payment_next_year or 0),
        "due_12mo_loans": due_12mo_loans,
        "overdue_usd": float(aggr.overdue_amount or 0),
        "overdue_loans": sum(1 for ln in loans if ln.date_due and ln.date_due < today and (ln.debt_usd or 0) > 0),
        "overdue_companies": len(overdue_companies),
        "fx_exposure_usd": non_uzs,
        "fx_exposure_pct": fx_exposure_pct,
        "expected_loss_usd": el_total,
        "expected_loss_loans": el_loans,
        "by_lender_type": by_lender,
        "by_currency": by_currency,
        "by_maturity": _maturity_list(),
        "as_of_date": str(aggr.as_of_date),
    }


@router.get("/drilldown/loans")
async def get_drilldown_loans(
    lender_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    maturity_bucket: Optional[str] = Query(None),
    is_guaranteed: Optional[bool] = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Drill-down: list loans matching filters."""
    from datetime import date as _date
    today = _date.today()

    filters = [CreditPortfolioLoan.deleted_at.is_(None)]
    if lender_type:
        filters.append(CreditPortfolioLoan.lender_type == lender_type)
    if currency:
        if currency == "OTHER":
            known = ["USD", "UZS", "CNY", "EUR", "JPY", "RUB", "SDR", "KZT", "GBP"]
            filters.append(~CreditPortfolioLoan.currency.in_(known))
        else:
            filters.append(CreditPortfolioLoan.currency == currency)
    if is_guaranteed is not None:
        filters.append(CreditPortfolioLoan.is_guaranteed == is_guaranteed)

    from app.models.company import Company
    rows = (await db.execute(
        select(CreditPortfolioLoan, Company.name_ru).join(
            Company, Company.id == CreditPortfolioLoan.company_id, isouter=True
        ).where(and_(*filters))
    )).all()

    out = []
    for ln, co_name in rows:
        debt = float(ln.debt_usd or 0)
        dtm = (ln.date_due - today).days if ln.date_due else 99999
        od = (today - ln.date_due).days if (ln.date_due and ln.date_due < today and debt > 0) else 0

        bucket = ("overdue" if od > 0 else "lt_1y" if dtm < 365 else "1_3y" if dtm < 365*3 else "3_5y" if dtm < 365*5 else "gt_5y")
        if maturity_bucket and bucket != maturity_bucket:
            continue
        if overdue_only and od == 0:
            continue
        out.append({
            "loan_id": str(ln.id),
            "loan_code": ln.loan_code,
            "bank": ln.bank,
            "bank_short_name": ln.bank_short_name,
            "company_name": co_name or "—",
            "borrower_unit": ln.borrower_unit,
            "lender_type": ln.lender_type,
            "currency": ln.currency,
            "rate": float(ln.rate) if ln.rate else None,
            "rate_text": ln.rate_text,
            "sum_total": float(ln.sum_total) if ln.sum_total else None,
            "debt_currency": float(ln.debt_currency) if ln.debt_currency else None,
            "debt_usd": debt or None,
            "date_get": ln.date_get.isoformat() if ln.date_get else None,
            "date_due": ln.date_due.isoformat() if ln.date_due else None,
            "is_guaranteed": bool(ln.is_guaranteed),
            "days_to_maturity": dtm,
            "overdue_days": od,
        })
    out.sort(key=lambda r: r["debt_usd"] or 0, reverse=True)
    return out[:limit]


@router.get("/drilldown/groups-by-company")
async def drilldown_by_company(
    lender_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    maturity_bucket: Optional[str] = Query(None),
    top_n: int = Query(12, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    loans = await get_drilldown_loans(lender_type, currency, maturity_bucket, None, False, 10000, db, _user)
    by_co = {}
    total = 0.0
    for ln in loans:
        name = ln["company_name"]
        d = ln["debt_usd"] or 0
        total += d
        if name not in by_co:
            by_co[name] = {"label_ru": name, "debt_usd": 0.0, "loans_count": 0, "banks": set()}
        by_co[name]["debt_usd"] += d
        by_co[name]["loans_count"] += 1
        by_co[name]["banks"].add(ln["bank_short_name"] or ln["bank"])
    rows = [{
        "key": n, "label_ru": n, "debt_usd": g["debt_usd"],
        "pct": (g["debt_usd"] / total * 100) if total > 0 else 0,
        "loans_count": g["loans_count"], "banks_count": len(g["banks"]),
    } for n, g in by_co.items()]
    rows.sort(key=lambda r: r["debt_usd"], reverse=True)
    return rows[:top_n]


@router.get("/drilldown/groups-by-bank")
async def drilldown_by_bank(
    lender_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    maturity_bucket: Optional[str] = Query(None),
    top_n: int = Query(12, le=50),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    loans = await get_drilldown_loans(lender_type, currency, maturity_bucket, None, False, 10000, db, _user)
    by_b = {}
    total = 0.0
    for ln in loans:
        name = ln["bank"]
        d = ln["debt_usd"] or 0
        total += d
        if name not in by_b:
            by_b[name] = {"label_ru": name, "debt_usd": 0.0, "loans_count": 0, "lender_type": ln["lender_type"]}
        by_b[name]["debt_usd"] += d
        by_b[name]["loans_count"] += 1
    rows = [{
        "key": n, "label_ru": n, "debt_usd": g["debt_usd"],
        "pct": (g["debt_usd"] / total * 100) if total > 0 else 0,
        "loans_count": g["loans_count"], "lender_type": g["lender_type"],
    } for n, g in by_b.items()]
    rows.sort(key=lambda r: r["debt_usd"], reverse=True)
    return rows[:top_n]


# ── Admin: apply migrations on demand ──
@router.post("/_apply-migrations")
async def apply_migrations_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admin endpoint — triggers Pack 7.41 self-heal."""
    _admin_only(user)
    from app.core.runtime_migrations_p741 import pack_741_self_heal
    return await pack_741_self_heal(db)
