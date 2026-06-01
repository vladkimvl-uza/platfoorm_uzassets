"""
Pydantic schemas for Credit Portfolio (Кредитный портфель) module.

Three groups:
  1. Read/write CRUD on individual loans
  2. Aggregation (single endpoint returns all stats for the dashboard)
  3. Bulk import / FX rates
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._types import MoneyDecimal

# ─── Read / detail ───────────────────────────────────────────────────

class LoanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    loan_code: str
    company_id: UUID
    company_name_ru: Optional[str] = None  # populated via join

    borrower_unit: Optional[str] = None

    bank: str
    bank_short_name: Optional[str] = None
    contract_ref: Optional[str] = None

    currency: str
    rate: Optional[MoneyDecimal] = None
    rate_text: Optional[str] = None

    sum_total: Optional[MoneyDecimal] = None
    sum_disbursed: Optional[MoneyDecimal] = None
    debt_currency: Optional[MoneyDecimal] = None
    debt_usd: Optional[MoneyDecimal] = None

    date_get: Optional[date] = None
    date_due: Optional[date] = None

    is_guaranteed: bool = False
    lender_type: Optional[str] = None

    auto_flags: dict = Field(default_factory=dict)
    notes: Optional[str] = None
    as_of_date: Optional[date] = None

    deleted_at: Optional[date] = None

    created_at: datetime
    updated_at: datetime


# ─── Create / update ─────────────────────────────────────────────────

class LoanCreate(BaseModel):
    """Create a new loan. `loan_code` must be unique across the portfolio."""

    loan_code: str = Field(..., min_length=1, max_length=32)
    company_id: UUID
    borrower_unit: Optional[str] = None

    bank: str = Field(..., min_length=1, max_length=255)
    bank_short_name: Optional[str] = None
    contract_ref: Optional[str] = None

    currency: str = Field(..., min_length=3, max_length=8)
    rate: Optional[MoneyDecimal] = None
    rate_text: Optional[str] = None

    sum_total: Optional[MoneyDecimal] = None
    sum_disbursed: Optional[MoneyDecimal] = None
    debt_currency: Optional[MoneyDecimal] = None
    debt_usd: Optional[MoneyDecimal] = None

    date_get: Optional[date] = None
    date_due: Optional[date] = None

    is_guaranteed: bool = False
    lender_type: Optional[str] = Field(None, pattern="^(bond|foreign|local|state)$")

    auto_flags: dict = Field(default_factory=dict)
    notes: Optional[str] = None
    as_of_date: Optional[date] = None


class LoanUpdate(BaseModel):
    """Partial update — every field is optional."""

    company_id: Optional[UUID] = None
    borrower_unit: Optional[str] = None

    bank: Optional[str] = None
    bank_short_name: Optional[str] = None
    contract_ref: Optional[str] = None

    currency: Optional[str] = None
    rate: Optional[MoneyDecimal] = None
    rate_text: Optional[str] = None

    sum_total: Optional[MoneyDecimal] = None
    sum_disbursed: Optional[MoneyDecimal] = None
    debt_currency: Optional[MoneyDecimal] = None
    debt_usd: Optional[MoneyDecimal] = None

    date_get: Optional[date] = None
    date_due: Optional[date] = None

    is_guaranteed: Optional[bool] = None
    lender_type: Optional[str] = None

    auto_flags: Optional[dict] = None
    notes: Optional[str] = None
    as_of_date: Optional[date] = None


# ─── Bulk import (Excel/JSON) ───────────────────────────────────────

class LoanBulkItem(LoanCreate):
    """Same as LoanCreate but `company_id` may be omitted in favor of
    `company_code` or `company_name_ru` for human-friendly imports."""
    company_id: Optional[UUID] = None
    company_code: Optional[str] = None
    company_name_ru: Optional[str] = None


class BulkImportRequest(BaseModel):
    items: list[LoanBulkItem]
    overwrite_existing: bool = Field(
        default=False,
        description=(
            "If true, loans with existing loan_code are updated; "
            "if false, they are skipped."
        ),
    )


class BulkImportResponse(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


# ─── Aggregation (dashboard) ────────────────────────────────────────

class CurrencyBreakdown(BaseModel):
    currency: str
    debt_usd: MoneyDecimal
    debt_currency: MoneyDecimal
    pct_of_total: float
    avg_rate: Optional[MoneyDecimal] = None
    loans_count: int


class LenderTypeBreakdown(BaseModel):
    lender_type: str
    label: str          # display label (e.g. "Бонд", "Иностранный")
    color: str          # hex color
    debt_usd: MoneyDecimal
    pct_of_total: float
    loans_count: int


class BankBreakdown(BaseModel):
    bank_short_name: str
    debt_usd: MoneyDecimal
    pct_of_total: float
    loans_count: int


class YearBucket(BaseModel):
    year: int
    debt_usd: MoneyDecimal
    loans_count: int


class MaturityBucket(BaseModel):
    bucket: str         # "overdue" | "<1 года" | "1-3 года" | "3-5 лет" | "5+ лет"
    debt_usd: MoneyDecimal
    loans_count: int


class TopLoanRef(BaseModel):
    """Reference to a loan that's notable in some KPI (e.g. largest payment)."""
    id: UUID
    loan_code: str
    bank: str
    bank_short_name: str
    company_name_ru: str
    debt_usd: MoneyDecimal
    date_due: Optional[date] = None
    days_until_due: Optional[int] = None
    currency: Optional[str] = None
    debt_currency: Optional[MoneyDecimal] = None
    rate: Optional[MoneyDecimal] = None


# ─── Risk Metrics (for Risks tab) ───────────────────────────────────

class RiskMetrics(BaseModel):
    """Risk-tab specific KPIs computed server-side from loans + financials."""
    ebitda_usd: Optional[MoneyDecimal] = None
    ebitda_year: Optional[int] = None
    ebitda_source_company: Optional[str] = None
    ebitda_unit_assumed: Optional[str] = None
    ebitda_sane: bool = False

    debt_to_ebitda: Optional[MoneyDecimal] = None       # totalUsd / EBITDA
    icr: Optional[MoneyDecimal] = None                   # EBITDA / annual interest expense
    annual_interest_expense_usd: MoneyDecimal           # sum(rate × debt_usd)

    refi_12mo_pct: float                            # %% of portfolio due <1 year
    concentration_top1_pct: float                   # %% in largest bank
    overdue_count: int
    overdue_amount_usd: MoneyDecimal


# ─── Risk Bubble Points (for risk scatter) ──────────────────────────

class RiskBubblePoint(BaseModel):
    loan_id: UUID
    loan_code: str
    bank: str
    bank_short_name: str
    currency: str
    years_to_due: float                  # x-axis
    rate_pct: float                      # y-axis
    debt_usd: MoneyDecimal                    # bubble size
    date_due: date


# ─── Sankey Flows (for Payments tab) ────────────────────────────────

class SankeyFlow(BaseModel):
    bank_short_name: str
    year_label: str           # "2026" or ">2030"
    debt_usd: MoneyDecimal


# ─── Bank Row (for full bank list, Lenders tab) ────────────────────

class BankRow(BaseModel):
    bank: str                 # full bank name
    bank_short_name: str
    lender_type: Optional[str] = None
    debt_usd: MoneyDecimal
    loans_count: int
    pct_of_total: float


# ─── Avg rate by (lender_type × currency) for "Средневзвеш ставки" ─

class RateMatrixCell(BaseModel):
    lender_type: str
    currency: str
    rate: MoneyDecimal              # decimal: 0.0985 = 9.85%
    debt_usd: MoneyDecimal           # weight
    loans_count: int


# ─── Per-company aggregate (for League Table on All-Companies overview) ─

class CompanyPaymentByYear(BaseModel):
    year: int                # use 9999 to mean ">2032"
    debt_usd: MoneyDecimal


class CompanyAggregateRow(BaseModel):
    """Per-company aggregation for the League Table view."""
    company_id: UUID
    company_name_ru: str
    company_code: Optional[str] = None
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None

    loans_count: int
    debt_usd: MoneyDecimal             # outstanding (net)
    loaned_total_usd: MoneyDecimal     # sum_total in USD
    repaid_total_usd: MoneyDecimal
    repaid_pct: float

    avg_rate: MoneyDecimal             # weighted by debt_usd
    payment_this_year: MoneyDecimal    # current year
    payment_next_year: MoneyDecimal

    # Annual payment breakdown for heatmap
    pay_by_year: list[CompanyPaymentByYear]
    pay_gt2032: MoneyDecimal           # all payments after 2032 collapsed


class CreditPortfolioAggregate(BaseModel):
    """Single response with all dashboard-level KPIs and breakdowns.

    Mirrors the monolith `cpCompute()` output structure 1:1 so the frontend
    can consume it directly without recomputation.
    """

    # Summary
    as_of_date: date
    total_usd: MoneyDecimal
    total_local: dict[str, MoneyDecimal]   # currency → debt in that currency
    loans_count: int
    banks_count: int
    avg_rate: MoneyDecimal                  # weighted by debt_usd

    # Loan facility totals (for "Кредитный портфель — выпл/ост" card)
    loaned_total_usd: MoneyDecimal
    repaid_total_usd: MoneyDecimal
    repaid_pct: float

    # Breakdowns
    by_currency: list[CurrencyBreakdown]
    by_lender_type: list[LenderTypeBreakdown]
    by_bank_top10: list[BankBreakdown]
    by_bank_full: list[BankRow]                # Full bank list w/ lender_type for Lenders tab
    by_year: list[YearBucket]
    by_bucket: list[MaturityBucket]
    rate_matrix: list[RateMatrixCell]          # type × currency rate matrix

    # Guaranteed vs unguaranteed
    guaranteed_amount: MoneyDecimal
    unguaranteed_amount: MoneyDecimal

    # Year-targeted KPIs
    payment_this_year: MoneyDecimal     # current year (e.g. 2026)
    payment_next_year: MoneyDecimal     # following year
    overdue_amount: MoneyDecimal

    # Notable loans
    top_payment_loan: Optional[TopLoanRef] = None
    nearest_payment_loan: Optional[TopLoanRef] = None

    # Per-currency average rates (for richer drill-downs)
    avg_rate_by_currency: dict[str, MoneyDecimal]


# ─── FX rates ───────────────────────────────────────────────────────

class FxRateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    as_of_date: date
    currency: str
    rate_to_uzs: MoneyDecimal
    notes: Optional[str] = None


class FxRateUpsert(BaseModel):
    as_of_date: date
    currency: str
    rate_to_uzs: MoneyDecimal
    notes: Optional[str] = None


# ─── Loan payments (manual repayment events) ────────────────────────

class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    loan_id: UUID
    paid_date: date
    principal_paid: MoneyDecimal
    interest_paid: MoneyDecimal
    penalty_paid: MoneyDecimal
    currency: str
    fx_rate_to_uzs: Optional[MoneyDecimal] = None
    note: Optional[str] = None
    created_by_user_id: Optional[UUID] = None
    created_at: Optional[datetime] = None


class PaymentCreate(BaseModel):
    paid_date: date
    principal_paid: MoneyDecimal
    interest_paid: MoneyDecimal = Decimal("0")
    penalty_paid: MoneyDecimal = Decimal("0")
    fx_rate_to_uzs: Optional[MoneyDecimal] = None
    note: Optional[str] = None


class PaymentUpdate(BaseModel):
    paid_date: Optional[date] = None
    principal_paid: Optional[MoneyDecimal] = None
    interest_paid: Optional[MoneyDecimal] = None
    penalty_paid: Optional[MoneyDecimal] = None
    fx_rate_to_uzs: Optional[MoneyDecimal] = None
    note: Optional[str] = None


class LoanPaymentsSummary(BaseModel):
    """Aggregate of all payments for one loan (lifetime totals)."""
    loan_id: UUID
    payments_count: int
    total_principal_paid: MoneyDecimal
    total_interest_paid: MoneyDecimal
    total_penalty_paid: MoneyDecimal
    last_paid_date: Optional[date] = None


# ─── Companies-with-loans (sidebar dropdown) ───────────────────────

class CompanyWithLoansRow(BaseModel):
    company_id: UUID
    company_name_ru: str
    company_code: Optional[str] = None
    sector: Optional[str] = None
    sector_color: Optional[str] = None
    loans_count: int
    debt_usd: MoneyDecimal


class CompaniesWithLoansResponse(BaseModel):
    items: list[CompanyWithLoansRow]
    total_loans: int
    total_debt_usd: MoneyDecimal
