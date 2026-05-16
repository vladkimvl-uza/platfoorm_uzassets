"""Pydantic schemas for /system-config endpoints (Pack 7.35).

Yearly Rates table — admin-editable system-wide constants stored in
year_registry: USD/UZS exchange rate and UZ Republic budget per year.
"""
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class YearlyRate(BaseModel):
    """Single year entry returned to admin UI."""
    year: int
    label: Optional[str] = None
    is_closed: bool = False

    # Editable system constants
    usd_rate: Optional[Decimal] = Field(
        default=None,
        description="Среднегодовой курс UZS за 1 USD",
    )
    eur_rate: Optional[Decimal] = Field(
        default=None,
        description="Среднегодовой курс UZS за 1 EUR",
    )
    uz_budget_trln: Optional[Decimal] = Field(
        default=None,
        description="Доходная часть бюджета Республики Узбекистан, трлн сум",
    )
    inflation_pct: Optional[Decimal] = Field(
        default=None,
        description="Годовая инфляция в Узбекистане, процент",
    )
    cb_rate_pct: Optional[Decimal] = Field(
        default=None,
        description="Базовая ставка Центрального Банка РУ, процент",
    )
    gdp_growth_pct: Optional[Decimal] = Field(
        default=None,
        description="Темп роста ВВП Узбекистана, процент",
    )

    class Config:
        from_attributes = True


class YearlyRateUpdate(BaseModel):
    """PATCH payload — any field may be null/omitted (partial update)."""
    label: Optional[str] = None
    is_closed: Optional[bool] = None
    usd_rate: Optional[Decimal] = None
    eur_rate: Optional[Decimal] = None
    uz_budget_trln: Optional[Decimal] = None
    inflation_pct: Optional[Decimal] = None
    cb_rate_pct: Optional[Decimal] = None
    gdp_growth_pct: Optional[Decimal] = None


class YearlyRateCreate(BaseModel):
    """POST payload — adds a new year row to the registry."""
    year: int = Field(..., ge=2000, le=2100)
    label: Optional[str] = None
    is_closed: bool = False
    usd_rate: Optional[Decimal] = None
    eur_rate: Optional[Decimal] = None
    uz_budget_trln: Optional[Decimal] = None
    inflation_pct: Optional[Decimal] = None
    cb_rate_pct: Optional[Decimal] = None
    gdp_growth_pct: Optional[Decimal] = None
