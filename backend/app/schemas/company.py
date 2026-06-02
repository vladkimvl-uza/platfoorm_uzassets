"""Pydantic schemas for the Companies API."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._types import MoneyDecimal

# =====================================================================
# Sectors (filter dropdowns)
# =====================================================================

class SectorBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    code: str
    name_ru: str
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    color_hex: Optional[str] = None
    sort_order: int
    company_count: Optional[int] = None


class SectorCreatePayload(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
    sort_order: int = 1000


class SectorUpdatePayload(BaseModel):
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
    sort_order: Optional[int] = None


# =====================================================================
# Company create / update payloads
# =====================================================================

class CompanyCreatePayload(BaseModel):
    code: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9_]+$",
                      description="Lowercase ASCII slug, used as ticker")
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_short: Optional[str] = Field(None, max_length=128)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    sector_code: Optional[str] = Field(None, description="Sector code, e.g. 'mining_metallurgy'")
    legal_form: Optional[str] = Field(None, max_length=64)
    inn: Optional[str] = Field(None, max_length=32)
    description: Optional[str] = None
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=512)
    ceo_name: Optional[str] = Field(None, max_length=255)
    employees_count: Optional[int] = Field(None, ge=0)
    founded_year: Optional[int] = Field(None, ge=1800, le=2100)


class CompanyUpdatePayload(BaseModel):
    """All fields optional — only those provided are updated."""
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_short: Optional[str] = Field(None, max_length=128)
    name_uz: Optional[str] = Field(None, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    sector_code: Optional[str] = None
    legal_form: Optional[str] = Field(None, max_length=64)
    inn: Optional[str] = Field(None, max_length=32)
    description: Optional[str] = None
    website: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=512)
    ceo_name: Optional[str] = Field(None, max_length=255)
    employees_count: Optional[int] = Field(None, ge=0)
    founded_year: Optional[int] = Field(None, ge=1800, le=2100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    hidden_years: Optional[list[int]] = None  # годы, в которых компания скрыта


# =====================================================================
# Companies
# =====================================================================

class CompanyListItem(BaseModel):
    """One row in the companies list view — light fields only, optimized for grid display."""
    id: UUID
    code: str
    name_ru: str
    name_short: Optional[str]
    sector_code: Optional[str]
    sector_name: Optional[str]
    sector_color: Optional[str]
    is_active: bool
    is_custom: bool
    hidden_years: Optional[list[int]] = None

    # Aggregated indicators (computed in the endpoint)
    governance_score: Optional[int] = None
    latest_revenue: Optional[MoneyDecimal] = None
    latest_revenue_year: Optional[int] = None
    has_financials: bool = False
    has_governance: bool = False


class CompanyListResponse(BaseModel):
    items: list[CompanyListItem]
    total: int
    sectors: list[SectorBrief]


class CompanyDetail(BaseModel):
    """Full company info for the detail view."""
    id: UUID
    code: str
    name_ru: str
    name_uz: Optional[str]
    name_en: Optional[str]
    name_short: Optional[str]
    legal_form: Optional[str]
    inn: Optional[str]
    sector: Optional[SectorBrief]
    description: Optional[str]
    logo_url: Optional[str]
    website: Optional[str]
    address: Optional[str]
    ceo_name: Optional[str]
    employees_count: Optional[int]
    founded_year: Optional[int]
    is_active: bool
    is_custom: bool
    extra: Optional[dict]
    hidden_years: Optional[list[int]] = None
    created_at: datetime
    updated_at: datetime


# =====================================================================
# Financials (drill-down on company page)
# =====================================================================

class FinancialLineBrief(BaseModel):
    line_code: str
    line_name: str
    value: Optional[MoneyDecimal]
    sort_order: int


class FinancialReportBrief(BaseModel):
    year: int
    quarter: Optional[int]
    standard: str
    report_type: str
    currency: str
    unit_scale: int
    source: str
    is_audited: bool
    notes: Optional[str]
    lines: list[FinancialLineBrief]


# =====================================================================
# Governance (drill-down on company page)
# =====================================================================

class GovernanceBrief(BaseModel):
    year: int
    board_size: Optional[int]
    independent_directors_count: Optional[int]
    women_directors_count: Optional[int]
    foreign_directors_count: Optional[int]
    avg_age: Optional[int]
    has_audit_committee: Optional[bool]
    has_strategy_committee: Optional[bool]
    meetings_per_year: Optional[int]
    avg_attendance_pct: Optional[int]
    score: Optional[int] = None  # extracted from payload
    payload: Optional[dict] = None


# =====================================================================
# Dashboard stats
# =====================================================================

class DashboardStats(BaseModel):
    companies_total: int
    companies_with_financials: int
    companies_with_governance: int
    sectors_count: int
    financial_reports_count: int
    announcements_published: int

    # Aggregates
    total_revenue_latest_year: Optional[MoneyDecimal] = None
    latest_revenue_year: Optional[int] = None
    average_governance_score: Optional[int] = None

    # Top performers
    top_governance_companies: list[dict] = Field(default_factory=list)
