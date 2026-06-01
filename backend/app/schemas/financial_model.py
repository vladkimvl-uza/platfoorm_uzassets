"""Schemas for the Финансовая модель API."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._types import MoneyDecimal

# ─── Catalog ──────────────────────────────────────────────────────────────

class CanonicalMetricEntry(BaseModel):
    """Reference catalog entry — used by the Vue UI to render rows."""

    code: str
    name_ru: str
    name_en: str
    section: str
    unit: str
    parent_code: Optional[str] = None
    indent: int = 0


class CanonicalCatalog(BaseModel):
    metrics: list[CanonicalMetricEntry]
    drivers: dict[str, dict[str, Any]]


# ─── Cells / drivers ──────────────────────────────────────────────────────

class MetricCell(BaseModel):
    """One (model × metric_code × year) cell."""

    metric_code: str
    metric_name_ru: str
    section: str
    parent_code: Optional[str] = None
    indent_level: int = 0
    year: int
    value: Optional[MoneyDecimal] = None
    unit: str = "UZSm"
    is_forecast: bool = False
    is_calculated: bool = False
    source_link: Optional[str] = None


class DriverCell(BaseModel):
    driver_code: str
    sub_code: str
    sub_name_ru: Optional[str] = None
    year: int
    value: Optional[MoneyDecimal] = None
    unit: str = "UZSm"


# ─── Model header ─────────────────────────────────────────────────────────

class FinancialModelSummary(BaseModel):
    """Slim representation for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_code: Optional[str] = None
    company_name_ru: Optional[str] = None
    scenario: str
    name: str
    status: str
    period_start: int
    period_end: int
    forecast_start: Optional[int] = None
    currency: str
    unit_scale: str
    updated_at: Optional[datetime] = None


class FinancialModelFull(FinancialModelSummary):
    """Full model: header + all metrics + all drivers."""

    wacc: Optional[MoneyDecimal] = None
    risk_free_rate: Optional[MoneyDecimal] = None
    beta: Optional[MoneyDecimal] = None
    market_premium: Optional[MoneyDecimal] = None
    country_premium: Optional[MoneyDecimal] = None
    cost_debt_pretax: Optional[MoneyDecimal] = None
    tax_rate: Optional[MoneyDecimal] = None
    equity_weight: Optional[MoneyDecimal] = None
    debt_weight: Optional[MoneyDecimal] = None
    terminal_growth: Optional[MoneyDecimal] = None
    notes: Optional[str] = None

    metrics: list[MetricCell] = Field(default_factory=list)
    drivers: list[DriverCell] = Field(default_factory=list)


# ─── Excel preview / confirm ──────────────────────────────────────────────

class ParsePreviewResponse(BaseModel):
    """Returned after multipart Excel upload — shows what would be imported."""

    period_start: int
    period_end: int
    forecast_start: Optional[int] = None
    metrics_total: int
    metrics_unmapped_count: int
    metrics_unmapped: list[str] = Field(default_factory=list)
    drivers_total: int
    warnings: list[str] = Field(default_factory=list)
    metrics: list[MetricCell] = Field(default_factory=list)
    drivers: list[DriverCell] = Field(default_factory=list)
    # Echo back so frontend can roundtrip into /import-confirm without re-uploading
    raw_excel_token: Optional[str] = None
    raw_filename: Optional[str] = None


class ImportConfirmRequest(BaseModel):
    company_code: str = Field(..., min_length=2, max_length=32)
    scenario: str = Field("base", min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=256)
    period_start: int = Field(..., ge=1990, le=2100)
    period_end: int = Field(..., ge=1990, le=2100)
    forecast_start: Optional[int] = Field(None, ge=1990, le=2100)
    currency: str = "UZS"
    unit_scale: str = "million"
    metrics: list[MetricCell]
    drivers: list[DriverCell] = Field(default_factory=list)
    overwrite: bool = False


# ─── Cell editing ─────────────────────────────────────────────────────────

class CellUpdateRequest(BaseModel):
    metric_code: str
    year: int
    value: Optional[MoneyDecimal] = None


class DriverCellUpdateRequest(BaseModel):
    driver_code: str
    sub_code: str
    year: int
    value: Optional[MoneyDecimal] = None


# ─── Header edit (WACC inputs etc.) ───────────────────────────────────────

class ModelHeaderUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None

    wacc: Optional[MoneyDecimal] = None
    risk_free_rate: Optional[MoneyDecimal] = None
    beta: Optional[MoneyDecimal] = None
    market_premium: Optional[MoneyDecimal] = None
    country_premium: Optional[MoneyDecimal] = None
    cost_debt_pretax: Optional[MoneyDecimal] = None
    tax_rate: Optional[MoneyDecimal] = None
    equity_weight: Optional[MoneyDecimal] = None
    debt_weight: Optional[MoneyDecimal] = None
    terminal_growth: Optional[MoneyDecimal] = None


# ─── Batch save (used by the editor modal) ────────────────────────────────

class BatchSaveCellChange(BaseModel):
    metric_code: str
    year: int
    value: Optional[MoneyDecimal] = None


class BatchSaveDriverChange(BaseModel):
    driver_code: str
    sub_code: str
    year: int
    value: Optional[MoneyDecimal] = None
    sub_name_ru: Optional[str] = None


class BatchSaveRequest(BaseModel):
    """Accept all editor changes in a single transactional call.

    Frontend collects pending edits as the user types and sends them all at
    once when "Сохранить" is clicked. Server applies header → cells → drivers
    in one DB transaction so the editor can never produce a partially-saved
    model.
    """

    cells: list[BatchSaveCellChange] = Field(default_factory=list)
    drivers: list[BatchSaveDriverChange] = Field(default_factory=list)
    header: Optional[ModelHeaderUpdateRequest] = None
