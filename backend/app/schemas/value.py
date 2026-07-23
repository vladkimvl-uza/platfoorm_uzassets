"""DTO реестра возможностей ценности (value opportunities)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

_SOURCES = {"unit_cost", "procurement", "business_plan", "kpi", "manual"}
_KINDS = {"economy", "uplift", "risk"}
_STATUSES = {"identified", "in_progress", "realized", "dismissed"}


class ValueOpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: Optional[UUID] = None
    company_name: Optional[str] = None
    sector_color: Optional[str] = None
    year: Optional[int] = None
    source: str
    kind: str
    status: str
    title: str
    description: Optional[str] = None
    value_amount: Optional[Decimal] = None
    realized_amount: Optional[Decimal] = None
    owner: Optional[str] = None
    target_date: Optional[date] = None
    realized_at: Optional[datetime] = None
    fingerprint: Optional[str] = None
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ValueOpportunityCreate(BaseModel):
    company_id: Optional[UUID] = None
    year: Optional[int] = None
    source: str = "manual"
    kind: str = "economy"
    status: str = "identified"
    title: str
    description: Optional[str] = None
    value_amount: Optional[Decimal] = None
    realized_amount: Optional[Decimal] = None
    owner: Optional[str] = None
    target_date: Optional[date] = None


class ValueOpportunityUpdate(BaseModel):
    company_id: Optional[UUID] = None
    year: Optional[int] = None
    source: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    value_amount: Optional[Decimal] = None
    realized_amount: Optional[Decimal] = None
    owner: Optional[str] = None
    target_date: Optional[date] = None


class ValueByStatus(BaseModel):
    status: str
    count: int = 0
    amount: float = 0.0        # Σ потенциала
    realized: float = 0.0      # Σ реализованного


class ValueByCompany(BaseModel):
    company_id: Optional[UUID] = None
    company_name: str
    sector_color: Optional[str] = None
    count: int = 0
    amount: float = 0.0
    realized: float = 0.0


class ValueSummary(BaseModel):
    total_count: int = 0
    identified_amount: float = 0.0    # потенциал в статусах identified+in_progress
    realized_amount: float = 0.0      # сумма реализованного (status=realized)
    in_progress_amount: float = 0.0
    by_status: list[ValueByStatus] = []
    by_source: list[ValueByStatus] = []   # переиспользуем shape (status=источник)
    by_company: list[ValueByCompany] = []
