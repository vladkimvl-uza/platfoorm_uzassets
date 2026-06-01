"""Credit Scenarios API — thin HTTP layer (refactored 2026-05-25).

Heavy compute (state_summary / debt_ratios / repayment_forecast / top_loans)
stays in existing core `app/services/credit_scenario_engine.py`.
Formula validation in `app/services/risk_formula_evaluator.py`.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.dependencies.credit_scenario import CreditScenarioServiceDep
from app.models.user import User
from app.schemas.credit_scenario import (
    CreditPortfolioScenarioCreate,
    CreditPortfolioScenarioOut,
    CreditPortfolioScenarioUpdate,
    CustomIndicatorCreate,
    CustomIndicatorOut,
    CustomIndicatorUpdate,
    DebtRatioRow,
    FormulaTestRequest,
    FormulaTestResponse,
    FormulaValidateRequest,
    FormulaValidateResponse,
    LoanScenarioOut,
    LoanScenarioUpdate,
    RepaymentQuarterRow,
    StateSummary,
    TopLoanRow,
)
from app.services.credit_scenario._helpers import admin_only
from app.services.credit_scenario_engine import (
    compute_debt_ratios,
    compute_repayment_forecast,
    compute_state_summary,
    compute_top_loans,
)
from app.services.risk_formula_evaluator import (
    DEFAULT_FORMULA_TEXT,
    DEFAULT_RR_BY_LENDER,
    validate_formula,
)

router = APIRouter(prefix="/credit-scenario", tags=["credit-scenario"])


# ─── Scenarios CRUD ──────────────────────────────────────────────

@router.get("/scenarios", response_model=list[CreditPortfolioScenarioOut])
async def list_scenarios(
    service: CreditScenarioServiceDep,
    _user: User = Depends(get_current_user),
):
    return await service.list_scenarios()


@router.get("/scenarios/{scenario_id}", response_model=CreditPortfolioScenarioOut)
async def get_scenario(
    scenario_id: UUID,
    service: CreditScenarioServiceDep,
    _user: User = Depends(get_current_user),
):
    return await service.get_scenario(scenario_id)


@router.post("/scenarios", response_model=CreditPortfolioScenarioOut, status_code=201)
async def create_scenario(
    body: CreditPortfolioScenarioCreate,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    return await service.create_scenario(body, actor_id=user.id)


@router.put("/scenarios/{scenario_id}", response_model=CreditPortfolioScenarioOut)
async def update_scenario(
    scenario_id: UUID,
    body: CreditPortfolioScenarioUpdate,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    return await service.update_scenario(scenario_id, body, actor_id=user.id)


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario(
    scenario_id: UUID,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    await service.delete_scenario(scenario_id)


# ─── Computed views (delegate to engine) ─────────────────────────

@router.get("/state-summary", response_model=StateSummary)
async def state_summary(
    scope: str = Query("all_uz"),
    scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await compute_state_summary(db, scope=scope, scenario_id=scenario_id)


@router.get("/debt-ratios", response_model=list[DebtRatioRow])
async def debt_ratios(
    scope: str = Query("all_uz"),
    top_n: int = Query(10, ge=1, le=22),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await compute_debt_ratios(db, scope=scope, top_n=top_n)


@router.get("/repayment-forecast", response_model=list[RepaymentQuarterRow])
async def repayment_forecast(
    scope: str = Query("all_uz"),
    years_back: int = Query(2, ge=0, le=10),
    years_forward: int = Query(5, ge=1, le=15),
    scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await compute_repayment_forecast(
        db, scope=scope, years_back=years_back,
        years_forward=years_forward, scenario_id=scenario_id,
    )


@router.get("/top-loans", response_model=list[TopLoanRow])
async def top_loans(
    scope: str = Query("all_uz"),
    top_n: int = Query(10, ge=1, le=50),
    scenario_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return await compute_top_loans(
        db, scope=scope, top_n=top_n, scenario_id=scenario_id,
    )


# ─── Per-loan overrides ──────────────────────────────────────────

@router.get("/loan-overrides/{scenario_id}", response_model=list[LoanScenarioOut])
async def list_loan_overrides(
    scenario_id: UUID,
    service: CreditScenarioServiceDep,
    _user: User = Depends(get_current_user),
):
    return await service.list_overrides(scenario_id)


@router.put("/loan-overrides/{scenario_id}/{loan_id}", response_model=LoanScenarioOut)
async def upsert_loan_override(
    scenario_id: UUID,
    loan_id: UUID,
    body: LoanScenarioUpdate,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    return await service.upsert_override(scenario_id, loan_id, body)


@router.delete("/loan-overrides/{scenario_id}/{loan_id}", status_code=204)
async def delete_loan_override(
    scenario_id: UUID,
    loan_id: UUID,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    await service.delete_override(scenario_id, loan_id)


# ─── Custom indicators ───────────────────────────────────────────

@router.get("/custom-indicators", response_model=list[CustomIndicatorOut])
async def list_custom_indicators(
    service: CreditScenarioServiceDep,
    _user: User = Depends(get_current_user),
):
    return await service.list_custom_indicators()


@router.post("/custom-indicators", response_model=CustomIndicatorOut, status_code=201)
async def create_custom_indicator(
    body: CustomIndicatorCreate,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    return await service.create_custom_indicator(body, actor_id=user.id)


@router.put("/custom-indicators/{indicator_id}", response_model=CustomIndicatorOut)
async def update_custom_indicator(
    indicator_id: UUID,
    body: CustomIndicatorUpdate,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    return await service.update_custom_indicator(indicator_id, body, actor_id=user.id)


@router.delete("/custom-indicators/{indicator_id}", status_code=204)
async def delete_custom_indicator(
    indicator_id: UUID,
    service: CreditScenarioServiceDep,
    user: User = Depends(get_current_user),
):
    admin_only(user)
    await service.delete_custom_indicator(indicator_id)


# ─── Formula validation / test ───────────────────────────────────

@router.post("/formula/validate", response_model=FormulaValidateResponse)
async def formula_validate(
    body: FormulaValidateRequest,
    _user: User = Depends(get_current_user),
):
    ok, err, pos, vars_used = validate_formula(body.formula_text)
    return FormulaValidateResponse(
        ok=ok, error=err, error_position=pos, variables_used=vars_used,
    )


@router.post("/formula/test", response_model=FormulaTestResponse)
async def formula_test(
    body: FormulaTestRequest,
    service: CreditScenarioServiceDep,
    _user: User = Depends(get_current_user),
):
    return await service.formula_test(
        body.formula_text, loan_id=body.loan_id,
    )


@router.get("/formula/default")
async def formula_default(_user: User = Depends(get_current_user)):
    return {"formula_text": DEFAULT_FORMULA_TEXT}


@router.get("/default-rr-by-lender")
async def default_rr(_user: User = Depends(get_current_user)):
    return DEFAULT_RR_BY_LENDER


# ─── Executive Dashboard overview + drilldowns ───────────────────

@router.get("/overview")
async def get_overview(
    service: CreditScenarioServiceDep,
    cp_scenario_id: Optional[UUID] = Query(None),
    user: User = Depends(get_current_user),
):
    return await service.overview(cp_scenario_id=cp_scenario_id, user=user)


@router.get("/drilldown/loans")
async def get_drilldown_loans(
    service: CreditScenarioServiceDep,
    lender_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    maturity_bucket: Optional[str] = Query(None),
    is_guaranteed: Optional[bool] = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(100, le=500),
    _user: User = Depends(get_current_user),
):
    return await service.drilldown_loans(
        lender_type=lender_type, currency=currency,
        maturity_bucket=maturity_bucket, is_guaranteed=is_guaranteed,
        overdue_only=overdue_only, limit=limit,
    )


@router.get("/drilldown/groups-by-company")
async def drilldown_by_company(
    service: CreditScenarioServiceDep,
    lender_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    maturity_bucket: Optional[str] = Query(None),
    top_n: int = Query(12, le=50),
    _user: User = Depends(get_current_user),
):
    return await service.drilldown_by_company(
        lender_type=lender_type, currency=currency,
        maturity_bucket=maturity_bucket, top_n=top_n,
    )


@router.get("/drilldown/groups-by-bank")
async def drilldown_by_bank(
    service: CreditScenarioServiceDep,
    lender_type: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    maturity_bucket: Optional[str] = Query(None),
    top_n: int = Query(12, le=50),
    _user: User = Depends(get_current_user),
):
    return await service.drilldown_by_bank(
        lender_type=lender_type, currency=currency,
        maturity_bucket=maturity_bucket, top_n=top_n,
    )


# ─── Admin: apply migrations ──────────────────────────────────────

@router.post("/_apply-migrations")
async def apply_migrations_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    admin_only(user)
    from app.core.runtime_migrations_p741 import pack_741_self_heal
    return await pack_741_self_heal(db)
