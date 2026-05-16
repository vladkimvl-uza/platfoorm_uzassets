"""
REST API for the Кредитный портфель (Credit Portfolio) module.

Endpoints:
    GET    /credit-portfolio/loans                    — list (filterable)
    GET    /credit-portfolio/loans/{id}               — detail
    POST   /credit-portfolio/loans                    — create
    PUT    /credit-portfolio/loans/{id}               — update
    DELETE /credit-portfolio/loans/{id}               — soft-delete
    POST   /credit-portfolio/loans/bulk               — bulk import
    GET    /credit-portfolio/aggregate                — full dashboard KPIs
    GET    /credit-portfolio/companies-with-loans     — sidebar dropdown
    GET    /credit-portfolio/fx-rates                 — FX rate snapshots
    PUT    /credit-portfolio/fx-rates                 — upsert rate

Permissions:
    `credit.view` — read all endpoints
    `credit.edit` — write CRUD + bulk
    `credit.delete` — DELETE
"""
from __future__ import annotations

import logging
from datetime import date as date_type
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.access import allowed_company_ids
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.models.company import Company, Sector
from app.models.credit import CreditPortfolioLoan, CreditPortfolioFxRate
from app.models.user import User
from app.schemas.credit_portfolio import (
    BankBreakdown,
    BankRow,
    BulkImportRequest,
    BulkImportResponse,
    CompaniesWithLoansResponse,
    CompanyAggregateRow,
    CompanyPaymentByYear,
    CompanyWithLoansRow,
    CreditPortfolioAggregate,
    CurrencyBreakdown,
    FxRateRead,
    FxRateUpsert,
    LenderTypeBreakdown,
    LoanBulkItem,
    LoanCreate,
    LoanRead,
    LoanUpdate,
    MaturityBucket,
    RateMatrixCell,
    RiskBubblePoint,
    RiskMetrics,
    SankeyFlow,
    TopLoanRef,
    YearBucket,
)
from app.services.credit_portfolio_helpers import (
    CURRENCY_COLORS,
    LENDER_TYPE_META,
    bank_short_name,
    classify_lender,
    days_between,
    maturity_bucket,
    year_of,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/credit-portfolio", tags=["credit-portfolio"])


# ─── Helpers ───────────────────────────────────────────────────────

async def _scope_query(db: AsyncSession, user: User, query):
    """Restrict loans query to companies user can access."""
    scope = await allowed_company_ids(db, user)
    if scope is not None:
        query = query.where(CreditPortfolioLoan.company_id.in_(list(scope)))
    return query


def _to_read(loan: CreditPortfolioLoan, company: Optional[Company] = None) -> LoanRead:
    """Convert DB loan + optional joined company into the API read schema."""
    payload = LoanRead.model_validate(loan)
    if company is not None:
        payload.company_name_ru = company.name_ru or company.name_en or company.code
    elif loan.company is not None:
        payload.company_name_ru = (
            loan.company.name_ru or loan.company.name_en or loan.company.code
        )
    return payload


# ─── List + filters ───────────────────────────────────────────────

@router.get("/loans", response_model=List[LoanRead])
async def list_loans(
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    currency: Optional[str] = Query(None),
    lender_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="match on bank or contract"),
    include_deleted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")

    q = select(CreditPortfolioLoan).options(selectinload(CreditPortfolioLoan.company))
    if not include_deleted:
        q = q.where(CreditPortfolioLoan.deleted_at.is_(None))
    if company_id:
        q = q.where(CreditPortfolioLoan.company_id == company_id)
    if company_code:
        company = (
            await db.execute(
                select(Company).where(func.lower(Company.code) == company_code.lower())
            )
        ).scalar_one_or_none()
        if company is None:
            return []
        q = q.where(CreditPortfolioLoan.company_id == company.id)
    if currency:
        q = q.where(CreditPortfolioLoan.currency == currency.upper())
    if lender_type:
        q = q.where(CreditPortfolioLoan.lender_type == lender_type)
    if search:
        like = f"%{search}%"
        q = q.where(
            CreditPortfolioLoan.bank.ilike(like)
            | CreditPortfolioLoan.contract_ref.ilike(like)
        )
    q = await _scope_query(db, user, q)
    q = q.order_by(CreditPortfolioLoan.debt_usd.desc().nullslast())

    rows = (await db.execute(q)).scalars().unique().all()
    return [_to_read(r) for r in rows]


# ─── Detail ────────────────────────────────────────────────────────

@router.get("/loans/{loan_id}", response_model=LoanRead)
async def get_loan(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")

    loan = (
        await db.execute(
            select(CreditPortfolioLoan)
            .where(CreditPortfolioLoan.id == loan_id)
            .options(selectinload(CreditPortfolioLoan.company))
        )
    ).scalar_one_or_none()
    if loan is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")
    scope = await allowed_company_ids(db, user)
    if scope is not None and loan.company_id not in scope:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access")
    return _to_read(loan)


# ─── Create ────────────────────────────────────────────────────────

@router.post("/loans", response_model=LoanRead, status_code=http_status.HTTP_201_CREATED)
async def create_loan(
    payload: LoanCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.edit required")

    # Verify company access
    scope = await allowed_company_ids(db, user)
    if scope is not None and payload.company_id not in scope:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to company")

    # Check uniqueness of loan_code
    existing = (
        await db.execute(
            select(CreditPortfolioLoan).where(CreditPortfolioLoan.loan_code == payload.loan_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            f"Loan code '{payload.loan_code}' already exists",
        )

    # Auto-classify lender_type if not provided
    auto_flags = dict(payload.auto_flags)
    lender_type = payload.lender_type
    if lender_type is None:
        lender_type = classify_lender(payload.bank)
        auto_flags["lenderType"] = True

    loan = CreditPortfolioLoan(
        loan_code=payload.loan_code,
        company_id=payload.company_id,
        borrower_unit=payload.borrower_unit,
        bank=payload.bank,
        bank_short_name=payload.bank_short_name or bank_short_name(payload.bank),
        contract_ref=payload.contract_ref,
        currency=payload.currency.upper(),
        rate=payload.rate,
        rate_text=payload.rate_text,
        sum_total=payload.sum_total,
        sum_disbursed=payload.sum_disbursed,
        debt_currency=payload.debt_currency,
        debt_usd=payload.debt_usd,
        date_get=payload.date_get,
        date_due=payload.date_due,
        is_guaranteed=payload.is_guaranteed,
        lender_type=lender_type,
        auto_flags=auto_flags,
        notes=payload.notes,
        as_of_date=payload.as_of_date,
        created_by_user_id=user.id,
    )
    db.add(loan)
    await db.commit()
    await db.refresh(loan)
    # Pack hotfix: load company eagerly to avoid lazy-load in _to_read
    company = None
    if loan.company_id:
        company = (await db.execute(select(Company).where(Company.id == loan.company_id))).scalar_one_or_none()
    return _to_read(loan, company=company)


# ─── Update ────────────────────────────────────────────────────────

@router.put("/loans/{loan_id}", response_model=LoanRead)
async def update_loan(
    loan_id: UUID,
    payload: LoanUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.edit required")

    loan = (
        await db.execute(
            select(CreditPortfolioLoan).where(CreditPortfolioLoan.id == loan_id)
        )
    ).scalar_one_or_none()
    if loan is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")

    scope = await allowed_company_ids(db, user)
    if scope is not None and loan.company_id not in scope:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(loan, k, v)
    if data.get("bank") and not data.get("bank_short_name"):
        loan.bank_short_name = bank_short_name(loan.bank)
    if data.get("currency"):
        loan.currency = loan.currency.upper()
    loan.updated_by_user_id = user.id

    await db.commit()
    await db.refresh(loan)
    # Pack hotfix: eager-load company
    company = None
    if loan.company_id:
        company = (await db.execute(select(Company).where(Company.id == loan.company_id))).scalar_one_or_none()
    return _to_read(loan, company=company)


# ─── Soft-delete ───────────────────────────────────────────────────

@router.delete("/loans/{loan_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_loan(
    loan_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.delete"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.delete required")

    loan = (
        await db.execute(
            select(CreditPortfolioLoan).where(CreditPortfolioLoan.id == loan_id)
        )
    ).scalar_one_or_none()
    if loan is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")
    scope = await allowed_company_ids(db, user)
    if scope is not None and loan.company_id not in scope:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access")

    loan.deleted_at = date_type.today()
    loan.updated_by_user_id = user.id
    await db.commit()


# ─── Bulk import ──────────────────────────────────────────────────

@router.post("/loans/bulk", response_model=BulkImportResponse)
async def bulk_import(
    payload: BulkImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.edit required")

    scope = await allowed_company_ids(db, user)
    inserted = updated = skipped = 0
    errors: List[str] = []

    # Resolve company refs (id, code, or name)
    co_by_id: Dict[UUID, Company] = {}
    co_by_code: Dict[str, Company] = {}
    co_by_name: Dict[str, Company] = {}
    for co in (await db.execute(select(Company))).scalars():
        co_by_id[co.id] = co
        if co.code:
            co_by_code[co.code.lower()] = co
        if co.name_ru:
            co_by_name[co.name_ru.strip().lower()] = co

    for item in payload.items:
        # Resolve company
        co: Optional[Company] = None
        if item.company_id:
            co = co_by_id.get(item.company_id)
        elif item.company_code:
            co = co_by_code.get(item.company_code.lower())
        elif item.company_name_ru:
            co = co_by_name.get(item.company_name_ru.strip().lower())

        if co is None:
            errors.append(
                f"loan {item.loan_code}: company not resolved "
                f"(id={item.company_id}, code={item.company_code}, name={item.company_name_ru})"
            )
            skipped += 1
            continue

        if scope is not None and co.id not in scope:
            errors.append(f"loan {item.loan_code}: no access to company {co.code}")
            skipped += 1
            continue

        existing = (
            await db.execute(
                select(CreditPortfolioLoan).where(
                    CreditPortfolioLoan.loan_code == item.loan_code
                )
            )
        ).scalar_one_or_none()

        # Auto-classification if not specified
        lender_type = item.lender_type or classify_lender(item.bank)
        auto_flags = dict(item.auto_flags or {})
        if not item.lender_type:
            auto_flags["lenderType"] = True

        if existing is not None:
            if not payload.overwrite_existing:
                skipped += 1
                continue
            existing.company_id = co.id
            existing.borrower_unit = item.borrower_unit
            existing.bank = item.bank
            existing.bank_short_name = item.bank_short_name or bank_short_name(item.bank)
            existing.contract_ref = item.contract_ref
            existing.currency = item.currency.upper()
            existing.rate = item.rate
            existing.rate_text = item.rate_text
            existing.sum_total = item.sum_total
            existing.sum_disbursed = item.sum_disbursed
            existing.debt_currency = item.debt_currency
            existing.debt_usd = item.debt_usd
            existing.date_get = item.date_get
            existing.date_due = item.date_due
            existing.is_guaranteed = item.is_guaranteed
            existing.lender_type = lender_type
            existing.auto_flags = auto_flags
            existing.notes = item.notes
            existing.as_of_date = item.as_of_date
            existing.updated_by_user_id = user.id
            updated += 1
        else:
            db.add(
                CreditPortfolioLoan(
                    loan_code=item.loan_code,
                    company_id=co.id,
                    borrower_unit=item.borrower_unit,
                    bank=item.bank,
                    bank_short_name=item.bank_short_name or bank_short_name(item.bank),
                    contract_ref=item.contract_ref,
                    currency=item.currency.upper(),
                    rate=item.rate,
                    rate_text=item.rate_text,
                    sum_total=item.sum_total,
                    sum_disbursed=item.sum_disbursed,
                    debt_currency=item.debt_currency,
                    debt_usd=item.debt_usd,
                    date_get=item.date_get,
                    date_due=item.date_due,
                    is_guaranteed=item.is_guaranteed,
                    lender_type=lender_type,
                    auto_flags=auto_flags,
                    notes=item.notes,
                    as_of_date=item.as_of_date,
                    created_by_user_id=user.id,
                )
            )
            inserted += 1

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"DB error during bulk import: {e}",
        )

    return BulkImportResponse(
        inserted=inserted, updated=updated, skipped=skipped, errors=errors
    )


# ─── Companies-with-loans (sidebar dropdown) ──────────────────────

@router.get("/companies-with-loans", response_model=CompaniesWithLoansResponse)
async def companies_with_loans(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await _companies_with_loans_impl(db, user)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[credit-portfolio /companies-with-loans] ERROR: {e}\n{tb}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"companies-with-loans failed: {type(e).__name__}: {e}",
        )


async def _companies_with_loans_impl(
    db: AsyncSession,
    user: User,
) -> "CompaniesWithLoansResponse":
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")

    # Note: Company.sector is a relationship — must JOIN the sectors table
    # to fetch the sector code/color, not select it directly.
    q = (
        select(
            Company.id,
            Company.code,
            Company.name_ru,
            Sector.code.label("sector_code"),
            Sector.color_hex.label("sector_color"),
            func.count(CreditPortfolioLoan.id).label("cnt"),
            func.coalesce(func.sum(CreditPortfolioLoan.debt_usd), 0).label("debt"),
        )
        .join(CreditPortfolioLoan, CreditPortfolioLoan.company_id == Company.id)
        .outerjoin(Sector, Company.sector_id == Sector.id)
        .where(CreditPortfolioLoan.deleted_at.is_(None))
        .group_by(
            Company.id,
            Company.code,
            Company.name_ru,
            Sector.code,
            Sector.color_hex,
        )
        .order_by(func.sum(CreditPortfolioLoan.debt_usd).desc().nullslast())
    )
    scope = await allowed_company_ids(db, user)
    if scope is not None:
        q = q.where(Company.id.in_(list(scope)))

    rows = (await db.execute(q)).all()

    # Fallback color map for sectors that don't have color_hex set
    fallback_colors = {
        "mining": "#9B8EC4",
        "metallurgy": "#9B8EC4",
        "oil_gas": "#0A7B5E",
        "energy": "#EF9F27",
        "transport": "#378ADD",
        "telecom": "#378ADD",
        "chemistry": "#888780",
        "other": "#888780",
    }

    items = [
        CompanyWithLoansRow(
            company_id=r.id,
            company_name_ru=r.name_ru or r.code,
            company_code=r.code,
            sector=r.sector_code,
            sector_color=r.sector_color or fallback_colors.get(r.sector_code or "", "#888780"),
            loans_count=int(r.cnt),
            debt_usd=Decimal(str(r.debt or 0)),
        )
        for r in rows
    ]
    return CompaniesWithLoansResponse(
        items=items,
        total_loans=sum(i.loans_count for i in items),
        total_debt_usd=sum((i.debt_usd for i in items), Decimal("0")),
    )


# ─── Aggregate (the dashboard endpoint) ───────────────────────────

@router.get("/aggregate", response_model=CreditPortfolioAggregate)
async def aggregate(
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None, description="defaults to global CP_AS_OF"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Single endpoint returning all dashboard KPIs.

    Mirrors monolith cpCompute() output. Server-side aggregation keeps the
    frontend simple and fast for ~316 loans.
    """
    try:
        return await _aggregate_impl(company_id, company_code, as_of, db, user)
    except HTTPException:
        raise
    except Exception as e:
        # Explicit error logging so the traceback is surfaced both in
        # docker logs AND in the response body for fast debugging.
        import traceback
        tb = traceback.format_exc()
        print(f"[credit-portfolio /aggregate] ERROR: {e}\n{tb}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"aggregate failed: {type(e).__name__}: {e}",
        )


async def _aggregate_impl(
    company_id: Optional[UUID],
    company_code: Optional[str],
    as_of: Optional[date_type],
    db: AsyncSession,
    user: User,
) -> "CreditPortfolioAggregate":
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")

    # Default as_of date (matches CP_AS_OF in the monolith)
    if as_of is None:
        as_of = date_type(2026, 1, 1)

    # Build query
    q = (
        select(CreditPortfolioLoan)
        .options(selectinload(CreditPortfolioLoan.company))
        .where(CreditPortfolioLoan.deleted_at.is_(None))
    )
    if company_id:
        q = q.where(CreditPortfolioLoan.company_id == company_id)
    if company_code:
        co = (
            await db.execute(
                select(Company).where(func.lower(Company.code) == company_code.lower())
            )
        ).scalar_one_or_none()
        if co is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
        q = q.where(CreditPortfolioLoan.company_id == co.id)
    q = await _scope_query(db, user, q)

    loans: List[CreditPortfolioLoan] = (
        (await db.execute(q)).scalars().unique().all()
    )

    if not loans:
        return CreditPortfolioAggregate(
            as_of_date=as_of,
            total_usd=Decimal("0"),
            total_local={},
            loans_count=0,
            banks_count=0,
            avg_rate=Decimal("0"),
            loaned_total_usd=Decimal("0"),
            repaid_total_usd=Decimal("0"),
            repaid_pct=0.0,
            by_currency=[],
            by_lender_type=[],
            by_bank_top10=[],
            by_bank_full=[],
            by_year=[],
            by_bucket=[],
            rate_matrix=[],
            guaranteed_amount=Decimal("0"),
            unguaranteed_amount=Decimal("0"),
            payment_this_year=Decimal("0"),
            payment_next_year=Decimal("0"),
            overdue_amount=Decimal("0"),
            top_payment_loan=None,
            nearest_payment_loan=None,
            avg_rate_by_currency={},
        )

    # Look up FX rates for the given as_of date (fallback: latest available)
    fx_rows = (
        await db.execute(
            select(CreditPortfolioFxRate).where(CreditPortfolioFxRate.as_of_date == as_of)
        )
    ).scalars().all()
    if not fx_rows:
        # fallback: latest available date
        latest = (
            await db.execute(
                select(CreditPortfolioFxRate).order_by(
                    CreditPortfolioFxRate.as_of_date.desc()
                )
            )
        ).scalars().first()
        if latest:
            fx_rows = (
                await db.execute(
                    select(CreditPortfolioFxRate).where(
                        CreditPortfolioFxRate.as_of_date == latest.as_of_date
                    )
                )
            ).scalars().all()

    fx: Dict[str, Decimal] = {f.currency: Decimal(str(f.rate_to_uzs)) for f in fx_rows}
    if "USD" not in fx:
        fx["USD"] = Decimal("12078.47")
    if "UZS" not in fx:
        fx["UZS"] = Decimal("1.0")

    # ─── Aggregation pass ───
    total_usd = Decimal("0")
    total_local: Dict[str, Decimal] = {}
    weighted_rate = Decimal("0")
    rate_base = Decimal("0")
    by_currency: Dict[str, Dict] = {}     # currency → {debt_usd, debt_cur, w, d, count}
    by_bank: Dict[str, Dict] = {}
    by_year: Dict[int, Dict] = {}
    by_bucket: Dict[str, Dict] = {}
    by_lender: Dict[str, Dict] = {}
    rate_by_currency: Dict[str, Dict] = {}  # currency → {w, d}
    rate_matrix: Dict[Tuple[str, str], Dict] = {}  # (lender_type, currency) → {w, d, count}
    guaranteed = Decimal("0")
    unguaranteed = Decimal("0")
    loaned_total = Decimal("0")
    repaid_total = Decimal("0")

    nearest_payment: Optional[CreditPortfolioLoan] = None
    top_payment_candidate: Optional[CreditPortfolioLoan] = None

    cur_year = as_of.year

    for ln in loans:
        debt_usd = Decimal(ln.debt_usd or 0)
        debt_cur = Decimal(ln.debt_currency or 0)
        currency = ln.currency
        rate = ln.rate
        bk = ln.bank_short_name or bank_short_name(ln.bank)
        lender_t = ln.lender_type or classify_lender(ln.bank)

        total_usd += debt_usd
        total_local[currency] = total_local.get(currency, Decimal("0")) + debt_cur

        # loaned/repaid
        sum_total = Decimal(ln.sum_total or 0)
        if debt_cur > 0 and debt_usd > 0:
            sum_total_usd = sum_total * (debt_usd / debt_cur)
        else:
            fx_cur = fx.get(currency, Decimal("1"))
            fx_usd = fx.get("USD", Decimal("12078.47"))
            sum_total_usd = (sum_total * fx_cur / fx_usd) if fx_usd else Decimal("0")
        if sum_total_usd == 0 and debt_usd > 0:
            sum_total_usd = debt_usd
        loaned_total += sum_total_usd
        repaid_total += max(Decimal("0"), sum_total_usd - debt_usd)

        # weighted rate
        if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
            weighted_rate += Decimal(rate) * debt_usd
            rate_base += debt_usd
            entry = rate_by_currency.setdefault(currency, {"w": Decimal("0"), "d": Decimal("0")})
            entry["w"] += Decimal(rate) * debt_usd
            entry["d"] += debt_usd

        # currency breakdown
        c = by_currency.setdefault(
            currency,
            {"debt_usd": Decimal("0"), "debt_cur": Decimal("0"), "count": 0,
             "rate_w": Decimal("0"), "rate_d": Decimal("0")},
        )
        c["debt_usd"] += debt_usd
        c["debt_cur"] += debt_cur
        c["count"] += 1
        if rate is not None and 0 < float(rate) < 1:
            c["rate_w"] += Decimal(rate) * debt_usd
            c["rate_d"] += debt_usd

        # bank breakdown — track full name + lender_type for richer display
        b = by_bank.setdefault(
            bk,
            {
                "debt_usd": Decimal("0"),
                "count": 0,
                "full_name": ln.bank,
                "lender_type": lender_t,
            },
        )
        b["debt_usd"] += debt_usd
        b["count"] += 1
        # If existing entry had no lender_type set, fill it now
        if not b.get("lender_type"):
            b["lender_type"] = lender_t

        # year & bucket
        yr = year_of(ln.date_due)
        if yr is not None:
            ye = by_year.setdefault(yr, {"debt_usd": Decimal("0"), "count": 0})
            ye["debt_usd"] += debt_usd
            ye["count"] += 1
        bu = maturity_bucket(ln.date_due, as_of)
        bo = by_bucket.setdefault(bu, {"debt_usd": Decimal("0"), "count": 0})
        bo["debt_usd"] += debt_usd
        bo["count"] += 1

        # lender
        lt = by_lender.setdefault(lender_t, {"debt_usd": Decimal("0"), "count": 0})
        lt["debt_usd"] += debt_usd
        lt["count"] += 1

        # Rate matrix: lender_type × currency (only valid rates)
        if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
            mtx_key = (lender_t, currency)
            mtx_e = rate_matrix.setdefault(
                mtx_key,
                {"w": Decimal("0"), "d": Decimal("0"), "count": 0},
            )
            mtx_e["w"] += Decimal(rate) * debt_usd
            mtx_e["d"] += debt_usd
            mtx_e["count"] += 1

        # guarantees
        if ln.is_guaranteed:
            guaranteed += debt_usd
        else:
            unguaranteed += debt_usd

        # nearest payment (within 1y) and top payment (largest within 1y)
        if ln.date_due is not None:
            d = days_between(as_of, ln.date_due)
            if d is not None and 0 <= d <= 365:
                if (
                    top_payment_candidate is None
                    or debt_usd > Decimal(top_payment_candidate.debt_usd or 0)
                ):
                    top_payment_candidate = ln
                if (
                    nearest_payment is None
                    or (ln.date_due < nearest_payment.date_due)
                ):
                    nearest_payment = ln

    avg_rate = (weighted_rate / rate_base) if rate_base else Decimal("0")

    # ─── Build response ───
    by_currency_list = []
    for cur, e in sorted(
        by_currency.items(), key=lambda x: -x[1]["debt_usd"]
    ):
        avg_r = (e["rate_w"] / e["rate_d"]) if e["rate_d"] else None
        by_currency_list.append(
            CurrencyBreakdown(
                currency=cur,
                debt_usd=e["debt_usd"],
                debt_currency=e["debt_cur"],
                pct_of_total=float(e["debt_usd"] / total_usd) if total_usd else 0.0,
                avg_rate=avg_r,
                loans_count=e["count"],
            )
        )

    by_lender_list = []
    for lt in ("bond", "foreign", "local", "state"):
        if lt not in by_lender:
            continue
        meta = LENDER_TYPE_META[lt]
        e = by_lender[lt]
        by_lender_list.append(
            LenderTypeBreakdown(
                lender_type=lt,
                label=meta["label"],
                color=meta["color"],
                debt_usd=e["debt_usd"],
                pct_of_total=float(e["debt_usd"] / total_usd) if total_usd else 0.0,
                loans_count=e["count"],
            )
        )
    by_lender_list.sort(key=lambda x: -x.debt_usd)

    by_bank_top10 = sorted(
        [
            BankBreakdown(
                bank_short_name=k,
                debt_usd=v["debt_usd"],
                pct_of_total=float(v["debt_usd"] / total_usd) if total_usd else 0.0,
                loans_count=v["count"],
            )
            for k, v in by_bank.items()
        ],
        key=lambda x: -x.debt_usd,
    )[:10]

    # Full bank list with lender_type for the Lenders tab table
    by_bank_full = sorted(
        [
            BankRow(
                bank=v["full_name"],
                bank_short_name=k,
                lender_type=v.get("lender_type"),
                debt_usd=v["debt_usd"],
                loans_count=v["count"],
                pct_of_total=float(v["debt_usd"] / total_usd) if total_usd else 0.0,
            )
            for k, v in by_bank.items()
        ],
        key=lambda x: -x.debt_usd,
    )

    rate_matrix_list = [
        RateMatrixCell(
            lender_type=lt,
            currency=cur,
            rate=(e["w"] / e["d"]) if e["d"] else Decimal("0"),
            debt_usd=e["d"],
            loans_count=e["count"],
        )
        for (lt, cur), e in rate_matrix.items()
        if e["d"] > 0
    ]
    rate_matrix_list.sort(key=lambda x: (x.lender_type, -x.debt_usd))

    by_year_list = sorted(
        [
            YearBucket(
                year=y, debt_usd=v["debt_usd"], loans_count=v["count"]
            )
            for y, v in by_year.items()
            if y >= as_of.year
        ],
        key=lambda x: x.year,
    )

    bucket_order = ("overdue", "<1 года", "1–3 года", "3–5 лет", ">5 лет", "unknown")
    by_bucket_list = [
        MaturityBucket(
            bucket=b,
            debt_usd=by_bucket[b]["debt_usd"],
            loans_count=by_bucket[b]["count"],
        )
        for b in bucket_order
        if b in by_bucket
    ]

    def _to_topref(ln: Optional[CreditPortfolioLoan]) -> Optional[TopLoanRef]:
        if ln is None:
            return None
        comp_name = (
            ln.company.name_ru
            if ln.company is not None and ln.company.name_ru
            else ""
        )
        return TopLoanRef(
            id=ln.id,
            loan_code=ln.loan_code,
            bank=ln.bank,
            bank_short_name=ln.bank_short_name or bank_short_name(ln.bank),
            company_name_ru=comp_name,
            debt_usd=Decimal(ln.debt_usd or 0),
            date_due=ln.date_due,
            days_until_due=days_between(as_of, ln.date_due) if ln.date_due else None,
            currency=ln.currency,
            debt_currency=Decimal(ln.debt_currency or 0),
            rate=Decimal(ln.rate) if ln.rate is not None else None,
        )

    return CreditPortfolioAggregate(
        as_of_date=as_of,
        total_usd=total_usd,
        total_local=total_local,
        loans_count=len(loans),
        banks_count=len(by_bank),
        avg_rate=avg_rate,
        loaned_total_usd=loaned_total,
        repaid_total_usd=repaid_total,
        repaid_pct=float(repaid_total / loaned_total) if loaned_total > 0 else 0.0,
        by_currency=by_currency_list,
        by_lender_type=by_lender_list,
        by_bank_top10=by_bank_top10,
        by_bank_full=by_bank_full,
        by_year=by_year_list,
        by_bucket=by_bucket_list,
        rate_matrix=rate_matrix_list,
        guaranteed_amount=guaranteed,
        unguaranteed_amount=unguaranteed,
        payment_this_year=Decimal(str(by_year.get(cur_year, {"debt_usd": 0})["debt_usd"])),
        payment_next_year=Decimal(str(by_year.get(cur_year + 1, {"debt_usd": 0})["debt_usd"])),
        overdue_amount=Decimal(str(by_bucket.get("overdue", {"debt_usd": 0})["debt_usd"])),
        top_payment_loan=_to_topref(top_payment_candidate),
        nearest_payment_loan=_to_topref(nearest_payment),
        avg_rate_by_currency={
            cur: (e["rate_w"] / e["rate_d"]) if e["rate_d"] else Decimal("0")
            for cur, e in by_currency.items()
        },
    )


# ─── Risk metrics ─────────────────────────────────────────────────

@router.get("/risk-metrics", response_model=RiskMetrics)
async def risk_metrics(
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Risk-tab specific KPIs: Debt/EBITDA, ICR, refi%, concentration, overdue."""
    try:
        return await _risk_metrics_impl(company_id, company_code, as_of, db, user)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[credit-portfolio /risk-metrics] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"risk-metrics failed: {type(e).__name__}: {e}",
        )


async def _risk_metrics_impl(
    company_id: Optional[UUID],
    company_code: Optional[str],
    as_of: Optional[date_type],
    db: AsyncSession,
    user: User,
) -> RiskMetrics:
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")
    if as_of is None:
        as_of = date_type(2026, 1, 1)

    q = (
        select(CreditPortfolioLoan)
        .where(CreditPortfolioLoan.deleted_at.is_(None))
    )
    if company_id:
        q = q.where(CreditPortfolioLoan.company_id == company_id)
    if company_code:
        co = (
            await db.execute(
                select(Company).where(func.lower(Company.code) == company_code.lower())
            )
        ).scalar_one_or_none()
        if co is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
        q = q.where(CreditPortfolioLoan.company_id == co.id)
    q = await _scope_query(db, user, q)

    loans = (await db.execute(q)).scalars().all()

    total_usd = sum((Decimal(l.debt_usd or 0) for l in loans), Decimal("0"))
    weighted_rate = Decimal("0")
    rate_base = Decimal("0")
    annual_interest = Decimal("0")
    overdue_count = 0
    overdue_amount = Decimal("0")
    refi_12mo = Decimal("0")
    by_bank: Dict[str, Decimal] = {}

    for ln in loans:
        debt_usd = Decimal(ln.debt_usd or 0)
        rate = ln.rate
        if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
            weighted_rate += Decimal(rate) * debt_usd
            rate_base += debt_usd

        bk = ln.bank_short_name or bank_short_name(ln.bank)
        by_bank[bk] = by_bank.get(bk, Decimal("0")) + debt_usd

        # Overdue & refi <1y
        if ln.date_due is not None:
            d = days_between(as_of, ln.date_due)
            if d is not None:
                if d < 0:
                    overdue_count += 1
                    overdue_amount += debt_usd
                if 0 <= d <= 365:
                    refi_12mo += debt_usd

    avg_rate = (weighted_rate / rate_base) if rate_base > 0 else Decimal("0")

    # Annual interest expense (use individual rate if valid, else avg_rate)
    for ln in loans:
        debt_usd = Decimal(ln.debt_usd or 0)
        rate = ln.rate
        if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
            annual_interest += debt_usd * Decimal(rate)
        else:
            annual_interest += debt_usd * avg_rate

    refi_12mo_pct = float(refi_12mo / total_usd) if total_usd > 0 else 0.0

    # Concentration: top-1 bank %% of total
    top_bank_amt = max(by_bank.values()) if by_bank else Decimal("0")
    concentration_pct = float(top_bank_amt / total_usd) if total_usd > 0 else 0.0

    # EBITDA from financials — heuristic for Узбекнефтегаз (matches monolith)
    ebitda_usd, ebitda_year, ebitda_src, ebitda_unit, ebitda_sane = await _resolve_ebitda(db)

    debt_to_ebitda = None
    icr = None
    if ebitda_sane and ebitda_usd and ebitda_usd > 0:
        debt_to_ebitda = total_usd / ebitda_usd if total_usd > 0 else None
        icr = ebitda_usd / annual_interest if annual_interest > 0 else None

    return RiskMetrics(
        ebitda_usd=ebitda_usd,
        ebitda_year=ebitda_year,
        ebitda_source_company=ebitda_src,
        ebitda_unit_assumed=ebitda_unit,
        ebitda_sane=ebitda_sane,
        debt_to_ebitda=debt_to_ebitda,
        icr=icr,
        annual_interest_expense_usd=annual_interest,
        refi_12mo_pct=refi_12mo_pct,
        concentration_top1_pct=concentration_pct,
        overdue_count=overdue_count,
        overdue_amount_usd=overdue_amount,
    )


async def _resolve_ebitda(
    db: AsyncSession,
) -> Tuple[Optional[Decimal], Optional[int], Optional[str], Optional[str], bool]:
    """Resolve Узбекнефтегаз EBITDA from the financials table.

    Returns: (ebitda_usd, year, source_company_name, unit_assumed, sane_flag)

    Sane range for oil&gas: $100M – $20B. Outside this range, ratios are not
    computed. Mirrors the cpGetEbitda() logic from the monolith.
    """
    # Try to import financials models — these may differ between deployments
    try:
        from app.models.financials_detailed import FinancialsDetailed  # type: ignore
    except Exception:
        return (None, None, None, None, False)

    # Find Узбекнефтегаз company
    co_q = select(Company).where(
        func.lower(Company.code).in_(["ung", "uzneftgaz", "uzbekneftegaz"])
    )
    co = (await db.execute(co_q)).scalar_one_or_none()
    if co is None:
        return (None, None, None, None, False)

    # Try to load most recent financials with EBITDA
    try:
        q = (
            select(FinancialsDetailed)
            .where(FinancialsDetailed.company_id == co.id)
            .order_by(FinancialsDetailed.year.desc())
        )
        rows = (await db.execute(q)).scalars().all()
    except Exception:
        return (None, None, None, None, False)

    fx_usd_uzs = Decimal("12078.47")
    for row in rows:
        # Heuristic search for ebitda field
        ebitda_raw = None
        for attr in ("ebitda", "ebitda_uzs", "ebitda_usd"):
            if hasattr(row, attr):
                v = getattr(row, attr)
                if v is not None and v != 0:
                    ebitda_raw = Decimal(str(v))
                    break
        if ebitda_raw is None:
            continue

        # Unit-assume heuristic from monolith
        if ebitda_raw > Decimal("1e9"):
            usd = ebitda_raw / fx_usd_uzs
            unit = "UZS (сумы)"
        elif ebitda_raw > Decimal("1e6"):
            usd = ebitda_raw * Decimal("1e6") / fx_usd_uzs
            unit = "млн UZS"
        elif ebitda_raw >= Decimal("100"):
            usd = ebitda_raw * Decimal("1e9") / fx_usd_uzs
            unit = "млрд UZS"
        elif ebitda_raw > 0:
            usd = ebitda_raw * Decimal("1e12") / fx_usd_uzs
            unit = "трлн UZS"
        else:
            continue

        sane = Decimal("1e8") < usd < Decimal("2e10")
        return (usd, row.year, co.name_ru or co.code, unit, sane)

    return (None, None, co.name_ru or co.code, None, False)


# ─── Risk Bubble Chart data ──────────────────────────────────────

@router.get("/risk-bubble", response_model=List[RiskBubblePoint])
async def risk_bubble(
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bubble chart data: x=years_to_due, y=rate%, size=debt_usd, color=currency."""
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")
    if as_of is None:
        as_of = date_type(2026, 1, 1)

    q = (
        select(CreditPortfolioLoan)
        .where(CreditPortfolioLoan.deleted_at.is_(None))
        .where(CreditPortfolioLoan.date_due.is_not(None))
        .where(CreditPortfolioLoan.rate.is_not(None))
    )
    if company_id:
        q = q.where(CreditPortfolioLoan.company_id == company_id)
    if company_code:
        co = (
            await db.execute(
                select(Company).where(func.lower(Company.code) == company_code.lower())
            )
        ).scalar_one_or_none()
        if co is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
        q = q.where(CreditPortfolioLoan.company_id == co.id)
    q = await _scope_query(db, user, q)

    loans = (await db.execute(q)).scalars().all()
    points = []
    for ln in loans:
        if ln.rate is None or Decimal(ln.rate) >= Decimal("1"):
            continue
        days = days_between(as_of, ln.date_due)
        if days is None:
            continue
        years_to = max(0.0, days / 365.25)
        points.append(
            RiskBubblePoint(
                loan_id=ln.id,
                loan_code=ln.loan_code,
                bank=ln.bank,
                bank_short_name=ln.bank_short_name or bank_short_name(ln.bank),
                currency=ln.currency,
                years_to_due=years_to,
                rate_pct=float(Decimal(ln.rate) * Decimal("100")),
                debt_usd=Decimal(ln.debt_usd or 0),
                date_due=ln.date_due,
            )
        )
    return points


# ─── Sankey Flows ─────────────────────────────────────────────────

@router.get("/sankey", response_model=List[SankeyFlow])
async def sankey_flows(
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    as_of: Optional[date_type] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bank → year flows (top-8 banks × years 2026-2030+) for the Payments sankey."""
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")
    if as_of is None:
        as_of = date_type(2026, 1, 1)

    q = (
        select(CreditPortfolioLoan)
        .where(CreditPortfolioLoan.deleted_at.is_(None))
        .where(CreditPortfolioLoan.date_due.is_not(None))
    )
    if company_id:
        q = q.where(CreditPortfolioLoan.company_id == company_id)
    if company_code:
        co = (
            await db.execute(
                select(Company).where(func.lower(Company.code) == company_code.lower())
            )
        ).scalar_one_or_none()
        if co is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
        q = q.where(CreditPortfolioLoan.company_id == co.id)
    q = await _scope_query(db, user, q)

    loans = (await db.execute(q)).scalars().all()

    # Aggregate by bank
    by_bank: Dict[str, Decimal] = {}
    for ln in loans:
        bk = ln.bank_short_name or bank_short_name(ln.bank)
        by_bank[bk] = by_bank.get(bk, Decimal("0")) + Decimal(ln.debt_usd or 0)

    top_banks = set(
        b for b, _ in sorted(by_bank.items(), key=lambda x: -x[1])[:8]
    )

    # Build flows
    flows: Dict[Tuple[str, str], Decimal] = {}
    base_year = as_of.year
    for ln in loans:
        bk = ln.bank_short_name or bank_short_name(ln.bank)
        if bk not in top_banks:
            continue
        y = year_of(ln.date_due)
        if y is None or y < base_year:
            continue
        # Buckets: each year through base_year+4, then ">YYYY"
        if y > base_year + 4:
            year_label = f">{base_year + 4}"
        else:
            year_label = str(y)
        key = (bk, year_label)
        flows[key] = flows.get(key, Decimal("0")) + Decimal(ln.debt_usd or 0)

    return [
        SankeyFlow(bank_short_name=bk, year_label=y, debt_usd=v)
        for (bk, y), v in flows.items()
        if v > 0
    ]


# ─── Companies overview (League Table) ────────────────────────────

@router.get("/companies-overview", response_model=List[CompanyAggregateRow])
async def companies_overview(
    as_of: Optional[date_type] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Per-company league-table aggregation for the All-Companies overview view."""
    try:
        return await _companies_overview_impl(as_of, db, user)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[credit-portfolio /companies-overview] ERROR: {e}\n{traceback.format_exc()}", flush=True)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"companies-overview failed: {type(e).__name__}: {e}",
        )


async def _companies_overview_impl(
    as_of: Optional[date_type],
    db: AsyncSession,
    user: User,
) -> List[CompanyAggregateRow]:
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")
    if as_of is None:
        as_of = date_type(2026, 1, 1)

    # Load all loans + companies + sectors in one go
    q = (
        select(CreditPortfolioLoan)
        .options(selectinload(CreditPortfolioLoan.company).selectinload(Company.sector))
        .where(CreditPortfolioLoan.deleted_at.is_(None))
    )
    q = await _scope_query(db, user, q)

    loans = (await db.execute(q)).scalars().unique().all()
    if not loans:
        return []

    # FX rates as fallback
    fx_rows = (
        await db.execute(
            select(CreditPortfolioFxRate).where(CreditPortfolioFxRate.as_of_date == as_of)
        )
    ).scalars().all()
    if not fx_rows:
        latest = (
            await db.execute(
                select(CreditPortfolioFxRate).order_by(
                    CreditPortfolioFxRate.as_of_date.desc()
                )
            )
        ).scalars().first()
        if latest:
            fx_rows = (
                await db.execute(
                    select(CreditPortfolioFxRate).where(
                        CreditPortfolioFxRate.as_of_date == latest.as_of_date
                    )
                )
            ).scalars().all()

    fx: Dict[str, Decimal] = {f.currency: Decimal(str(f.rate_to_uzs)) for f in fx_rows}
    if "USD" not in fx:
        fx["USD"] = Decimal("12078.47")

    fallback_colors = {
        "mining": "#9B8EC4",
        "metallurgy": "#9B8EC4",
        "oil_gas": "#0A7B5E",
        "energy": "#EF9F27",
        "transport": "#378ADD",
        "telecom": "#378ADD",
        "chemistry": "#888780",
        "other": "#888780",
    }

    # Group by company
    cur_year = as_of.year
    per_co: Dict[UUID, Dict] = {}

    for ln in loans:
        co = ln.company
        if co is None:
            continue
        debt_usd = Decimal(ln.debt_usd or 0)
        sum_total = Decimal(ln.sum_total or 0)

        # Compute sum_total in USD
        if Decimal(ln.debt_currency or 0) > 0 and debt_usd > 0:
            sum_total_usd = sum_total * (debt_usd / Decimal(ln.debt_currency or 1))
        else:
            fx_cur = fx.get(ln.currency, Decimal("1"))
            fx_usd = fx.get("USD", Decimal("12078.47"))
            sum_total_usd = (sum_total * fx_cur / fx_usd) if fx_usd else Decimal("0")
        if sum_total_usd == 0 and debt_usd > 0:
            sum_total_usd = debt_usd

        bucket = per_co.setdefault(
            co.id,
            {
                "company": co,
                "loans_count": 0,
                "debt_usd": Decimal("0"),
                "loaned": Decimal("0"),
                "repaid": Decimal("0"),
                "rate_w": Decimal("0"),
                "rate_d": Decimal("0"),
                "pay_by_year": {},  # year → Decimal
                "pay_gt2032": Decimal("0"),
            },
        )
        bucket["loans_count"] += 1
        bucket["debt_usd"] += debt_usd
        bucket["loaned"] += sum_total_usd
        bucket["repaid"] += max(Decimal("0"), sum_total_usd - debt_usd)

        if ln.rate is not None and Decimal(0) < Decimal(ln.rate) < Decimal(1):
            bucket["rate_w"] += Decimal(ln.rate) * debt_usd
            bucket["rate_d"] += debt_usd

        y = year_of(ln.date_due)
        if y is not None:
            if y > 2032:
                bucket["pay_gt2032"] += debt_usd
            else:
                bucket["pay_by_year"][y] = bucket["pay_by_year"].get(y, Decimal("0")) + debt_usd

    # Build response rows
    rows: List[CompanyAggregateRow] = []
    for cid, e in per_co.items():
        co = e["company"]
        sector_code = co.sector.code if co.sector else None
        sector_color = (
            (co.sector.color_hex if co.sector and co.sector.color_hex else None)
            or fallback_colors.get(sector_code or "", "#888780")
        )
        avg_rate = (e["rate_w"] / e["rate_d"]) if e["rate_d"] > 0 else Decimal("0")
        repaid_pct = float(e["repaid"] / e["loaned"]) if e["loaned"] > 0 else 0.0

        pay_by_year_list = [
            CompanyPaymentByYear(year=y, debt_usd=v)
            for y, v in sorted(e["pay_by_year"].items())
        ]

        rows.append(
            CompanyAggregateRow(
                company_id=co.id,
                company_name_ru=co.name_ru or co.code,
                company_code=co.code,
                sector_code=sector_code,
                sector_color=sector_color,
                loans_count=e["loans_count"],
                debt_usd=e["debt_usd"],
                loaned_total_usd=e["loaned"],
                repaid_total_usd=e["repaid"],
                repaid_pct=repaid_pct,
                avg_rate=avg_rate,
                payment_this_year=e["pay_by_year"].get(cur_year, Decimal("0")),
                payment_next_year=e["pay_by_year"].get(cur_year + 1, Decimal("0")),
                pay_by_year=pay_by_year_list,
                pay_gt2032=e["pay_gt2032"],
            )
        )

    # Sort by debt_usd desc by default
    rows.sort(key=lambda r: -r.debt_usd)
    return rows


# ─── FX rates ─────────────────────────────────────────────────────

@router.get("/fx-rates", response_model=List[FxRateRead])
async def list_fx_rates(
    as_of: Optional[date_type] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.view required")

    q = select(CreditPortfolioFxRate)
    if as_of:
        q = q.where(CreditPortfolioFxRate.as_of_date == as_of)
    q = q.order_by(
        CreditPortfolioFxRate.as_of_date.desc(),
        CreditPortfolioFxRate.currency,
    )
    rows = (await db.execute(q)).scalars().all()
    return [FxRateRead.model_validate(r) for r in rows]


@router.put("/fx-rates", response_model=FxRateRead)
async def upsert_fx_rate(
    payload: FxRateUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "credit.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "credit.edit required")

    existing = (
        await db.execute(
            select(CreditPortfolioFxRate).where(
                and_(
                    CreditPortfolioFxRate.as_of_date == payload.as_of_date,
                    CreditPortfolioFxRate.currency == payload.currency.upper(),
                )
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.rate_to_uzs = payload.rate_to_uzs
        existing.notes = payload.notes
    else:
        existing = CreditPortfolioFxRate(
            as_of_date=payload.as_of_date,
            currency=payload.currency.upper(),
            rate_to_uzs=payload.rate_to_uzs,
            notes=payload.notes,
        )
        db.add(existing)

    await db.commit()
    await db.refresh(existing)
    return FxRateRead.model_validate(existing)
