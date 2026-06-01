"""Pydantic schemas — Pack 7.41 credit scenarios.

Read/write contracts for the credit-portfolio scenarios admin section.
"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._types import MoneyDecimal


# ============================================================================
# Credit Portfolio Scenario
# ============================================================================
class CreditPortfolioScenarioBase(BaseModel):
    macro_scenario_key: str = Field(..., max_length=64)
    name_ru: Optional[str] = Field(None, max_length=255)
    state_forgiveness_pct: Optional[MoneyDecimal] = None
    refinance_rate_delta_pp: Optional[MoneyDecimal] = None
    default_rate_pct: Optional[MoneyDecimal] = None
    repayment_acceleration_pct: Optional[MoneyDecimal] = None
    risk_formula_text: Optional[str] = None
    risk_rr_by_lender: dict = Field(default_factory=dict)
    extra: dict = Field(default_factory=dict)


class CreditPortfolioScenarioCreate(CreditPortfolioScenarioBase):
    pass


class CreditPortfolioScenarioUpdate(BaseModel):
    name_ru: Optional[str] = Field(None, max_length=255)
    state_forgiveness_pct: Optional[MoneyDecimal] = None
    refinance_rate_delta_pp: Optional[MoneyDecimal] = None
    default_rate_pct: Optional[MoneyDecimal] = None
    repayment_acceleration_pct: Optional[MoneyDecimal] = None
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
    forgiveness_pct: Optional[MoneyDecimal] = None
    rate_override: Optional[MoneyDecimal] = None
    rescheduled_to: Optional[date] = None
    default_probability: Optional[MoneyDecimal] = None
    partial_repayment_pct: Optional[MoneyDecimal] = None
    custom_params: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class LoanScenarioCreate(LoanScenarioBase):
    pass


class LoanScenarioUpdate(BaseModel):
    forgiveness_pct: Optional[MoneyDecimal] = None
    rate_override: Optional[MoneyDecimal] = None
    rescheduled_to: Optional[date] = None
    default_probability: Optional[MoneyDecimal] = None
    partial_repayment_pct: Optional[MoneyDecimal] = None
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
    min_value: Optional[MoneyDecimal] = None
    max_value: Optional[MoneyDecimal] = None
    current_value: Optional[MoneyDecimal] = None
    formula_text: Optional[str] = None
    aggregation: Optional[str] = Field(None, max_length=16)
    source_metric: Optional[str] = None
    tooltip_ru: Optional[str] = None


class CustomIndicatorCreate(CustomIndicatorBase):
    pass


class CustomIndicatorUpdate(BaseModel):
    name_ru: Optional[str] = Field(None, max_length=255)
    input_type: Optional[str] = Field(None, max_length=16)
    min_value: Optional[MoneyDecimal] = None
    max_value: Optional[MoneyDecimal] = None
    current_value: Optional[MoneyDecimal] = None
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
    value: MoneyDecimal
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
    sum_total_usd: MoneyDecimal  # total facility size (portfolio)
    debt_outstanding_usd: MoneyDecimal  # outstanding
    repaid_usd: MoneyDecimal
    repaid_pct: MoneyDecimal
    guaranteed_usd: MoneyDecimal
    guaranteed_pct: MoneyDecimal
    avg_rate_pct: MoneyDecimal
    fx_exposure_pct: MoneyDecimal  # non-UZS share
    overdue_usd: MoneyDecimal
    overdue_count: int
    expected_loss_usd: MoneyDecimal
    flagged_loans_count: int
    next_12mo_payments_usd: MoneyDecimal


class DebtRatioRow(BaseModel):
    company_id: UUID
    company_name: str
    debt_usd: MoneyDecimal
    ebitda_usd: Optional[MoneyDecimal] = None
    revenue_usd: Optional[MoneyDecimal] = None
    fcf_usd: Optional[MoneyDecimal] = None
    debt_service_usd: Optional[MoneyDecimal] = None
    debt_to_ebitda: Optional[MoneyDecimal] = None
    debt_to_revenue: Optional[MoneyDecimal] = None
    icr: Optional[MoneyDecimal] = None  # Interest Coverage Ratio
    fcf_debt_service: Optional[MoneyDecimal] = None
    risk_zone: str  # "green" / "amber" / "red"


class RepaymentQuarterRow(BaseModel):
    period_year: int
    period_quarter: int  # 1..4 (or 0 for year-aggregated row)
    scheduled_usd: MoneyDecimal
    paid_usd: MoneyDecimal
    overdue_usd: MoneyDecimal
    forgiven_usd: MoneyDecimal
    custom_usd: MoneyDecimal
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
    debt_usd: MoneyDecimal
    rate: Optional[MoneyDecimal]
    date_due: Optional[date]
    # Scenario override fields (nullable if no override set yet)
    forgiveness_pct: Optional[MoneyDecimal] = None
    rate_override: Optional[MoneyDecimal] = None
    rescheduled_to: Optional[date] = None
    default_probability: Optional[MoneyDecimal] = None
    partial_repayment_pct: Optional[MoneyDecimal] = None
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
    final_value: Optional[MoneyDecimal] = None
