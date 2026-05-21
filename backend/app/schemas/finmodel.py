"""FinModel v2 Pydantic schemas — Phase 1.3."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─── Template ────────────────────────────────────────────────────────
class TemplateRowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    code: str
    section: str
    order_idx: int
    parent_code: Optional[str] = None
    row_type: str
    name_ru: str
    name_uz: Optional[str] = None
    name_uz_cyr: Optional[str] = None
    name_en: Optional[str] = None
    formula: Optional[str] = None
    # Exposed as `dashboard_category` for clarity; persisted in `ifrs_category`
    # column (reusing existing schema until IFRS mapping is implemented).
    dashboard_category: Optional[str] = Field(default=None, validation_alias="ifrs_category")
    sign_convention: Optional[str] = None
    is_indent: int = 0
    legacy_note: Optional[str] = None


# ─── Cell value ──────────────────────────────────────────────────────
class CellValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_code: str
    value: Optional[Decimal] = None
    is_calculated: bool = False
    updated_at: Optional[datetime] = None


class CellWrite(BaseModel):
    row_code: str
    value: Optional[Decimal] = None


class CellBatchWrite(BaseModel):
    cells: List[CellWrite]


# ─── Macro ───────────────────────────────────────────────────────────
class MacroValues(BaseModel):
    uz_inflation: Optional[Decimal] = None
    us_inflation: Optional[Decimal] = None
    uzs_usd_avg_rate: Optional[Decimal] = None
    uzs_eur_avg_rate: Optional[Decimal] = None
    uzs_rub_avg_rate: Optional[Decimal] = None
    uzs_cny_avg_rate: Optional[Decimal] = None


class MacroGlobalRead(MacroValues):
    model_config = ConfigDict(from_attributes=True)
    year: int
    updated_at: Optional[datetime] = None


class MacroCompanyWrite(MacroValues):
    forecast_method: Optional[str] = Field(default="uz_inflation")
    manual_growth_pct: Optional[Decimal] = None
    dividend_payout_ratio: Optional[Decimal] = None


class MacroCompanyRead(MacroCompanyWrite):
    model_config = ConfigDict(from_attributes=True)
    company_id: UUID
    year: int
    updated_at: Optional[datetime] = None


class MacroEffective(MacroValues):
    """Resolved macro for a (company, year) — company override falls back to global."""
    year: int
    source: Dict[str, str] = Field(default_factory=dict)  # field → 'company' | 'global' | 'none'


# ─── Year lock ───────────────────────────────────────────────────────
class YearLockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    year: int
    status: str
    locked_at: Optional[datetime] = None
    locked_by: Optional[UUID] = None
    approval_note: Optional[str] = None


class YearLockUpdate(BaseModel):
    status: str
    approval_note: Optional[str] = None


# ─── Year data (full snapshot for one year) ─────────────────────────
class YearDataRead(BaseModel):
    company_id: UUID
    year: int
    lock: YearLockRead
    macro: MacroEffective
    cells: List[CellValueRead]
    # Quick aggregates computed by engine for UI sanity check
    balance_check: Dict[str, Any] = Field(default_factory=dict)


# ─── Scenarios ───────────────────────────────────────────────────────
class ScenarioCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


# ─── Comments ────────────────────────────────────────────────────────
class CommentCreate(BaseModel):
    row_code: str
    comment_text: str
    source_ref: Optional[str] = None


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    year: int
    row_code: str
    comment_text: str
    source_ref: Optional[str] = None
    author_id: Optional[UUID] = None
    created_at: datetime


# ─── Audit ───────────────────────────────────────────────────────────
class AuditEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    year: int
    row_code: str
    value_before: Optional[Decimal] = None
    value_after: Optional[Decimal] = None
    actor_id: Optional[UUID] = None
    source: str
    ts: datetime


class AuditList(BaseModel):
    items: List[AuditEntry]
    total: int


# ─── Validation ──────────────────────────────────────────────────────
class ValidationIssue(BaseModel):
    rule_id: str
    severity: str  # error | warning | info
    row_code: Optional[str] = None
    message_ru: str
    message_en: Optional[str] = None


# ─── Forecast ────────────────────────────────────────────────────────
class ForecastRequest(BaseModel):
    base_year: int  # source year (last fact)
    target_years: List[int]  # years to forecast
    method: str = Field(default="uz_inflation")  # uz_inflation | manual | cagr_5y
