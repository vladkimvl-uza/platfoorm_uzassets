"""IFRS report history schemas — даты публикации МСФО-отчётности."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IfrsHistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    year: int
    published_on: Optional[date] = None
    updated_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None


class IfrsHistoryLastChange(BaseModel):
    by_name: Optional[str] = None
    at: Optional[datetime] = None


class IfrsHistoryResponse(BaseModel):
    rows: list[IfrsHistoryRow]
    last_change: IfrsHistoryLastChange


class IfrsHistoryUpsert(BaseModel):
    published_on: Optional[date] = None   # null = очистить дату
