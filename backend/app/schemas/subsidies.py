"""Subsidies registry schemas — реестр субсидий."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._types import MoneyDecimal


class SubsidyRow(BaseModel):
    """A single subsidy record (joined with company + sector for the registry)."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    sector_color: Optional[str] = None

    year: Optional[int] = None
    amount: Optional[MoneyDecimal] = None
    program: Optional[str] = None
    source: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    allocation_date: Optional[date] = None
    note: Optional[str] = None

    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SubsidyUpsert(BaseModel):
    """Create / update payload. company_id + year required on create."""
    company_id: UUID
    year: Optional[int] = None
    amount: Optional[float] = Field(None, ge=0)
    program: Optional[str] = Field(None, max_length=512)
    source: Optional[str] = Field(None, max_length=255)
    kind: Optional[str] = Field(None, max_length=128)
    status: Optional[str] = Field(None, max_length=32)
    allocation_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=8000)


class SubsidyPatch(BaseModel):
    """Partial update — все поля опциональны."""
    year: Optional[int] = None
    amount: Optional[float] = Field(None, ge=0)
    program: Optional[str] = Field(None, max_length=512)
    source: Optional[str] = Field(None, max_length=255)
    kind: Optional[str] = Field(None, max_length=128)
    status: Optional[str] = Field(None, max_length=32)
    allocation_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=8000)


class SubsidyCompanyAgg(BaseModel):
    company_id: UUID
    company_name: Optional[str] = None
    company_code: Optional[str] = None
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    sector_color: Optional[str] = None
    total: MoneyDecimal
    count: int


class SubsidySectorAgg(BaseModel):
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    sector_color: Optional[str] = None
    total: MoneyDecimal
    count: int


class SubsidySummary(BaseModel):
    """Aggregate for the «Субсидии» metric card (scope + year + sector filtered)."""
    year: Optional[int] = None
    sector_code: Optional[str] = None
    total: MoneyDecimal
    count: int
    by_company: list[SubsidyCompanyAgg] = Field(default_factory=list)
    by_sector: list[SubsidySectorAgg] = Field(default_factory=list)
