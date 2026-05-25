"""REST API for the Кредитный портфель (Credit Portfolio) module — thin HTTP
shim (refactored 2026-05-25). All business logic lives in
`app.services.credit_portfolio.service.CreditPortfolioService`.

Endpoints:
    GET    /credit-portfolio/loans                          — list (filterable)
    GET    /credit-portfolio/loans/{id}                     — detail
    POST   /credit-portfolio/loans                          — create
    PUT    /credit-portfolio/loans/{id}                     — update
    DELETE /credit-portfolio/loans/{id}                     — soft-delete
    POST   /credit-portfolio/loans/bulk                     — bulk import
    GET    /credit-portfolio/aggregate                      — dashboard KPIs
    GET    /credit-portfolio/risk-metrics                   — Debt/EBITDA, ICR…
    GET    /credit-portfolio/risk-bubble                    — bubble chart
    GET    /credit-portfolio/sankey                         — bank→year flows
    GET    /credit-portfolio/companies-overview             — league table
    GET    /credit-portfolio/companies-with-loans           — sidebar dropdown
    GET    /credit-portfolio/fx-rates                       — list FX
    PUT    /credit-portfolio/fx-rates                       — upsert FX
    GET    /credit-portfolio/loans/{id}/payments            — payments list
    POST   /credit-portfolio/loans/{id}/payments            — add payment
    GET    /credit-portfolio/loans/{id}/payments/summary    — payments totals
    GET    /credit-portfolio/payments/{id}                  — payment detail
    PATCH  /credit-portfolio/payments/{id}                  — edit
    DELETE /credit-portfolio/payments/{id}                  — soft-delete

Permissions:
    credit.view — read; credit.edit — write CRUD + bulk + payments;
    credit.delete — loan DELETE.
"""
from __future__ import annotations

import logging
import traceback
from datetime import date as date_type
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from app.core.security import get_current_user
from app.dependencies.credit_portfolio import CreditPortfolioServiceDep
from app.models.user import User
from app.schemas.credit_portfolio import (
    BulkImportRequest, BulkImportResponse,
    CompaniesWithLoansResponse, CompanyAggregateRow,
    CreditPortfolioAggregate,
    FxRateRead, FxRateUpsert,
    LoanCreate, LoanPaymentsSummary, LoanRead, LoanUpdate,
    PaymentCreate, PaymentRead, PaymentUpdate,
    RiskBubblePoint, RiskMetrics, SankeyFlow,
)


log = logging.getLogger(__name__)
router = APIRouter(prefix="/credit-portfolio", tags=["credit-portfolio"])


def _surface_500(label: str):
    """Wrap an awaitable in a try/except that mirrors the old error-logging
    pattern: full traceback to stdout + traceback-prefixed detail body."""
    def decorate(fn):
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[credit-portfolio {label}] ERROR: {e}\n{tb}", flush=True)
                raise HTTPException(
                    http_status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"{label} failed: {type(e).__name__}: {e}",
                )
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        wrapper.__wrapped__ = fn
        return wrapper
    return decorate


# ─── Loans CRUD ───────────────────────────────────────────────────

@router.get("/loans", response_model=List[LoanRead])
async def list_loans(
    service: CreditPortfolioServiceDep,
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    lender_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="match on bank or contract"),
    include_deleted: bool = Query(False),
    user: User = Depends(get_current_user),
):
    return await service.list_loans(
        user,
        company_id=company_id,
        company_code=company_code,
        currency=currency,
        lender_type=lender_type,
        search=search,
        include_deleted=include_deleted,
    )


@router.get("/loans/{loan_id}", response_model=LoanRead)
async def get_loan(
    loan_id: UUID,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.get_loan(loan_id, user)


@router.post(
    "/loans", response_model=LoanRead, status_code=http_status.HTTP_201_CREATED
)
async def create_loan(
    payload: LoanCreate,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.create_loan(payload, user)


@router.put("/loans/{loan_id}", response_model=LoanRead)
async def update_loan(
    loan_id: UUID,
    payload: LoanUpdate,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.update_loan(loan_id, payload, user)


@router.delete("/loans/{loan_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_loan(
    loan_id: UUID,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    await service.delete_loan(loan_id, user)


@router.post("/loans/bulk", response_model=BulkImportResponse)
async def bulk_import(
    payload: BulkImportRequest,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.bulk_import(payload, user)


# ─── Sidebar / League table ───────────────────────────────────────

@router.get("/companies-with-loans", response_model=CompaniesWithLoansResponse)
@_surface_500("/companies-with-loans")
async def companies_with_loans(
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.companies_with_loans(user)


@router.get("/companies-overview", response_model=List[CompanyAggregateRow])
@_surface_500("/companies-overview")
async def companies_overview(
    service: CreditPortfolioServiceDep,
    as_of: Optional[date_type] = Query(None),
    user: User = Depends(get_current_user),
):
    return await service.companies_overview(user, as_of=as_of)


# ─── Aggregate / Risk / Bubble / Sankey ───────────────────────────

@router.get("/aggregate", response_model=CreditPortfolioAggregate)
@_surface_500("/aggregate")
async def aggregate(
    service: CreditPortfolioServiceDep,
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None, description="defaults to global CP_AS_OF"),
    user: User = Depends(get_current_user),
):
    return await service.aggregate(
        user, company_id=company_id, company_code=company_code, as_of=as_of
    )


@router.get("/risk-metrics", response_model=RiskMetrics)
@_surface_500("/risk-metrics")
async def risk_metrics(
    service: CreditPortfolioServiceDep,
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None),
    user: User = Depends(get_current_user),
):
    return await service.risk_metrics(
        user, company_id=company_id, company_code=company_code, as_of=as_of
    )


@router.get("/risk-bubble", response_model=List[RiskBubblePoint])
async def risk_bubble(
    service: CreditPortfolioServiceDep,
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None),
    user: User = Depends(get_current_user),
):
    return await service.risk_bubble(
        user, company_id=company_id, company_code=company_code, as_of=as_of
    )


@router.get("/sankey", response_model=List[SankeyFlow])
async def sankey_flows(
    service: CreditPortfolioServiceDep,
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None),
    user: User = Depends(get_current_user),
):
    return await service.sankey(
        user, company_id=company_id, company_code=company_code, as_of=as_of
    )


# ─── FX rates ─────────────────────────────────────────────────────

@router.get("/fx-rates", response_model=List[FxRateRead])
async def list_fx_rates(
    service: CreditPortfolioServiceDep,
    as_of: Optional[date_type] = Query(None),
    user: User = Depends(get_current_user),
):
    return await service.list_fx_rates(user, as_of=as_of)


@router.put("/fx-rates", response_model=FxRateRead)
async def upsert_fx_rate(
    payload: FxRateUpsert,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.upsert_fx_rate(payload, user)


# ─── Payments ─────────────────────────────────────────────────────

@router.get("/loans/{loan_id}/payments", response_model=List[PaymentRead])
async def list_loan_payments(
    loan_id: UUID,
    service: CreditPortfolioServiceDep,
    include_deleted: bool = Query(False),
    user: User = Depends(get_current_user),
):
    return await service.list_loan_payments(
        loan_id, user, include_deleted=include_deleted
    )


@router.post(
    "/loans/{loan_id}/payments",
    response_model=PaymentRead,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_loan_payment(
    loan_id: UUID,
    payload: PaymentCreate,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.create_loan_payment(loan_id, payload, user)


@router.get(
    "/loans/{loan_id}/payments/summary", response_model=LoanPaymentsSummary
)
async def get_loan_payments_summary(
    loan_id: UUID,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.loan_payments_summary(loan_id, user)


@router.get("/payments/{payment_id}", response_model=PaymentRead)
async def get_payment(
    payment_id: UUID,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.get_payment(payment_id, user)


@router.patch("/payments/{payment_id}", response_model=PaymentRead)
async def update_payment(
    payment_id: UUID,
    payload: PaymentUpdate,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.update_payment(payment_id, payload, user)


@router.delete(
    "/payments/{payment_id}", status_code=http_status.HTTP_204_NO_CONTENT
)
async def delete_payment(
    payment_id: UUID,
    service: CreditPortfolioServiceDep,
    user: User = Depends(get_current_user),
):
    await service.delete_payment(payment_id, user)
