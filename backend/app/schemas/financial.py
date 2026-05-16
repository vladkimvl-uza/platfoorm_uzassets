"""Schemas for the Financials editor — bulk edit of financial_reports + lines."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# Catalog: full list of line codes from monolith (for editor UI rows)
# =====================================================================

class FinancialLineCatalogEntry(BaseModel):
    """Reference catalog entry for the editor UI — defines available line codes."""
    code: str
    name_ru: str
    name_en: Optional[str] = None
    parent_code: Optional[str] = None
    is_subtotal: bool = False
    sort_order: int = 0


# =====================================================================
# Editor: full report view (one company × one year × one standard)
# =====================================================================

class FinancialLineEdit(BaseModel):
    line_code: str = Field(..., min_length=1, max_length=32)
    line_name: str = Field(..., min_length=1, max_length=512)
    line_name_uz: Optional[str] = Field(None, max_length=512)
    line_name_en: Optional[str] = Field(None, max_length=512)
    parent_code: Optional[str] = Field(None, max_length=32)
    value: Optional[Decimal] = None
    is_subtotal: bool = False
    is_calculated: bool = False
    sort_order: int = 0


class FinancialReportFull(BaseModel):
    """Full editable financial report with all its lines."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None

    year: int
    quarter: Optional[int] = None
    standard: str  # IFRS | NSBU
    report_type: str  # PL | BS | CF
    currency: str = "UZS"
    unit_scale: int = 1000  # 1=units, 1000=thousands, 1000000=millions
    source: str = "manual"
    is_audited: bool = False
    notes: Optional[str] = None
    extra: Optional[dict] = None

    lines: List[FinancialLineEdit]

    created_at: datetime
    updated_at: datetime
    # Server-side checksum for the editor's verify-after-save protocol
    checksum: Optional[str] = None


class FinancialReportSavePayload(BaseModel):
    """PUT /financials/{report_id} — full replace with anti-loss verify hooks.

    Editor flow:
      1. Client computes `expected_checksum` from local state
      2. Server replaces ALL lines, recomputes checksum, returns it
      3. Client verifies returned checksum matches expectations
      4. If client-side `verify_get_after = true`, client immediately
         GETs the report again and re-verifies — surfaces silent corruption
    """
    year: int = Field(..., ge=1990, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)
    standard: str = Field("IFRS", pattern="^(IFRS|NSBU)$")
    report_type: str = Field("PL", pattern="^(PL|BS|CF)$")
    currency: str = Field("UZS", min_length=3, max_length=8)
    unit_scale: int = Field(1000, ge=1)
    source: str = Field("manual", min_length=1, max_length=32)
    is_audited: bool = False
    notes: Optional[str] = None
    extra: Optional[dict] = None

    lines: List[FinancialLineEdit] = Field(..., min_length=0)

    # Client's expected checksum BEFORE this save (for optimistic concurrency).
    # If server's current checksum != this, returns 409 Conflict (someone else saved).
    expected_prev_checksum: Optional[str] = None


class FinancialReportSaveResponse(BaseModel):
    """Response from a save/PUT — includes server-recomputed checksum and post-save line count."""
    report: FinancialReportFull
    saved_at: datetime
    lines_total: int
    # Post-save verification: client should compare these to its local state
    server_checksum: str


class FinancialReportListItem(BaseModel):
    """Light row for the report-picker dropdown in editor."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_code: str
    year: int
    quarter: Optional[int] = None
    standard: str
    report_type: str
    is_audited: bool
    lines_count: int = 0
    updated_at: datetime


class FinancialReportCreatePayload(BaseModel):
    """POST /financials — create a new (empty) report."""
    company_id: UUID
    year: int = Field(..., ge=1990, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)
    standard: str = Field("IFRS", pattern="^(IFRS|NSBU)$")
    report_type: str = Field("PL", pattern="^(PL|BS|CF)$")
    currency: str = Field("UZS", min_length=3, max_length=8)
    unit_scale: int = Field(1000, ge=1)
    source: str = Field("manual", min_length=1, max_length=32)


class CatalogResponse(BaseModel):
    """Editor reference data: line codes catalog."""
    line_codes: List[FinancialLineCatalogEntry]
    standards: List[str] = Field(default_factory=lambda: ["IFRS", "NSBU"])
    report_types: List[dict] = Field(default_factory=lambda: [
        {"code": "PL", "name_ru": "Отчёт о прибылях и убытках", "name_en": "P&L"},
        {"code": "BS", "name_ru": "Бухгалтерский баланс",        "name_en": "Balance Sheet"},
        {"code": "CF", "name_ru": "Отчёт о движении ДС",         "name_en": "Cash Flow"},
    ])
    unit_scales: List[dict] = Field(default_factory=lambda: [
        {"value": 1,        "label_ru": "сум",      "short": "UZS"},
        {"value": 1000,     "label_ru": "тыс. сум", "short": "тыс."},
        {"value": 1000000,  "label_ru": "млн сум",  "short": "млн"},
        {"value": 1000000000, "label_ru": "млрд сум", "short": "млрд"},
    ])
