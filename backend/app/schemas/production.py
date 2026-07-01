"""Pydantic bodies for Production indicators. Overview/import responses are
plain dicts (as in forensic); only editor upsert is typed."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ProductionLineIn(BaseModel):
    name: str
    unit: Optional[str] = None
    total: bool = False
    parent: Optional[int] = None
    # raw natura / money for base(2025 fact) / plan / expected / fact(факт) —
    # производные (темп/исполнение) считает сервис. fact — фактический результат
    # периода; если введён, исполнение считается факт/план (иначе ожид/план).
    baseN: Optional[float] = None
    baseM: Optional[float] = None
    planN: Optional[float] = None
    planM: Optional[float] = None
    expN: Optional[float] = None
    expM: Optional[float] = None
    factN: Optional[float] = None
    factM: Optional[float] = None


class ProductionUpsert(BaseModel):
    """Полная замена данных одной компании за (year, period) — редактор."""
    year: int = Field(..., ge=2000, le=2100)
    period: str = "h1"
    lines: list[ProductionLineIn] = Field(default_factory=list)
