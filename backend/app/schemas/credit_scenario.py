"""Pydantic schemas — Pack 7.41 credit scenarios.

Read/write contracts for the credit-portfolio scenarios admin section.
"""
from typing import Optional, Any
from decimal import Decimal
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# Credit Portfolio Scenario
# ============================================================================
class CreditPortfolioScenarioBase(BaseModel):
    macro_scenario_key: str = Field(..., max_length=64)
    name_ru: Optional[str] = Field(None, max_length=255)
    state_forgiveness_pct: Optional[Decimal] = None
    refinance_rate_delta_pp: Optional[Decimal] = None
    default_rate_pct: Optional[Decimal] = None
    repayment_acceleration_pct: Optional[Decimal] = None
    risk_formula_text: Optional[str] = None
    risk_rr_by_lender: dict = Field(default_factory=dict)
    extra: dict = Field(default_factory=dict)


class CreditPortfolioScenarioCreate(CreditPortfolioScenarioBase):
    pass


class CreditPortfolioScenarioUpdate(BaseModel):
    name_ru: Optional[str] = Field(None, max_length=255)
    state_forgiveness_pct: Optional[Decimal] = None
    refinance_rate_delta_pp: Optional[Decimal] = None
    default_rate_pct: Optional[Decimal] = None
    repayment_acceleration_pct: Optional[Decimal] = None
    risk_formula_text: Optional[str] = None
    risk_rr_by_lender: Optional[dict] = None
    extra: Optional[dict] = None


class CreditPortfolioScenarioOut(CreditPortfolioScenarioBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None


# ============================================================================
# Per-loan override
# ============================================================================
class LoanScenarioBase(BaseModel):
    scenario_id: UUID
    loan_id: UUID
    forgiveness_pct: Optional[Decimal] = None
    rate_override: Optional[Decimal] = None
    rescheduled_to: Optional[date] = None
    default_probability: Optional[Decimal] = None
    partial_repayment_pct: Optional[Decimal] = None
    custom_params: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class LoanScenarioCreate(LoanScenarioBase):
    pass


class LoanScenarioUpdate(BaseModel):
    forgiveness_pct: Optional[Decimal] = None
    rate_override: Optional[Decimal] = None
    rescheduled_to: Optional[date] = None
    default_probability: Optional[Decimal] = None
    partial_repayment_pct: Optional[Decimal] = None
    custom_params: Optional[dict] = None
    notes: Optional[str] = None


class LoanScenarioOut(LoanScenarioBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ============================================================================
# Custom indicator
# ============================================================================
class CustomIndicatorBase(BaseModel):
    key: str = Field(..., max_length=64)
    name_ru: str = Field(..., max_length=255)
    input_type: str = Field(..., max_length=16)
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    formula_text: Optional[str] = None
    aggregation: Optional[str] = Field(None, max_length=16)
    source_metric: Optional[str] = None
    tooltip_ru: Optional[str] = None


class CustomIndicatorCreate(CustomIndicatorBase):
    pass


class CustomIndicatorUpdate(BaseModel):
    name_ru: Optional[str] = Field(None, max_length=255)
    input_type: Optional[str] = Field(None, max_length=16)
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    current_value: Optional[Decimal] = None
    formula_text: Optional[str] = None
    aggregation: Optional[str] = Field(None, max_length=16)
    source_metric: Optional[str] = None
    tooltip_ru: Optional[str] = None


class CustomIndicatorOut(CustomIndicatorBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


# ============================================================================
# Computed results — what the admin section displays
# ============================================================================
class CreditKpi(BaseModel):
    label: str
    value: Decimal
    unit: str
    count: Optional[int] = None
    extra: dict = Field(default_factory=dict)


class StateSummary(BaseModel):
    """Top-level KPI strip for the admin credit-nagruzka section."""
    # Scope-aware aggregates
    scope: str  # "all_uz" / "state" / "local" / "foreign" / "all"
    loans_count: int
    companies_count: int
    banks_count: int
    sum_total_usd: Decimal  # total facility size (portfolio)
    debt_outstanding_usd: Decimal  # outstanding
    repaid_usd: Decimal
    repaid_pct: Decimal
    guaranteed_usd: Decimal
    guaranteed_pct: Decimal
    avg_rate_pct: Decimal
    fx_exposure_pct: Decimal  # non-UZS share
    overdue_usd: Decimal
    overdue_count: int
    expected_loss_usd: Decimal
    flagged_loans_count: int
    next_12mo_payments_usd: Decimal


class DebtRatioRow(BaseModel):
    company_id: UUID
    company_name: str
    debt_usd: Decimal
    ebitda_usd: Optional[Decimal] = None
    revenue_usd: Optional[Decimal] = None
    fcf_usd: Optional[Decimal] = None
    debt_service_usd: Optional[Decimal] = None
    debt_to_ebitda: Optional[Decimal] = None
    debt_to_revenue: Optional[Decimal] = None
    icr: Optional[Decimal] = None  # Interest Coverage Ratio
    fcf_debt_service: Optional[Decimal] = None
    risk_zone: str  # "green" / "amber" / "red"


class RepaymentQuarterRow(BaseModel):
    period_year: int
    period_quarter: int  # 1..4 (or 0 for year-aggregated row)
    scheduled_usd: Decimal
    paid_usd: Decimal
    overdue_usd: Decimal
    forgiven_usd: Decimal
    custom_usd: Decimal
    is_custom: bool  # any custom schedule in this quarter
    is_history: bool  # year < current year


class TopLoanRow(BaseModel):
    """One row of the TOP-N loans table with overrides."""
    loan_id: UUID
    loan_code: str
    bank: str
    company_name: str
    lender_type: Optional[str]
    is_guaranteed: bool
    debt_usd: Decimal
    rate: Optional[Decimal]
    date_due: Optional[date]
    # Scenario override fields (nullable if no override set yet)
    forgiveness_pct: Optional[Decimal] = None
    rate_override: Optional[Decimal] = None
    rescheduled_to: Optional[date] = None
    default_probability: Optional[Decimal] = None
    partial_repayment_pct: Optional[Decimal] = None
    notes: Optional[str] = None


# ============================================================================
# Formula validation/test
# ============================================================================
class FormulaValidateRequest(BaseModel):
    formula_text: str


class FormulaValidateResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    error_position: Optional[int] = None
    variables_used: list[str] = Field(default_factory=list)


class FormulaTestRequest(BaseModel):
    formula_text: str
    loan_id: Optional[UUID] = None  # if None, use first eligible loan


class FormulaTestResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    loan_code: Optional[str] = None
    inputs: dict = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    final_value: Optional[Decimal] = None
