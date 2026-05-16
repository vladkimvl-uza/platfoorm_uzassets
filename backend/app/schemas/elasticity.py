"""Pack 7.43 — Pydantic schemas for elasticity & project effects."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Literal
from uuid import UUID as PyUUID

from pydantic import BaseModel, Field, ConfigDict

from app.models.elasticity import MACRO_FACTORS, TARGET_METRICS


MacroFactor = Literal[
    "inflation_pct", "cb_rate_pct", "usd_rate", "eur_rate",
    "gdp_growth_pct", "oil_price_brent",
]
TargetMetric = Literal[
    "revenue", "ebitda", "opex", "capex", "debt_service", "net_income",
]


class ElasticityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: PyUUID
    scenario_id: Optional[PyUUID]
    company_id: Optional[PyUUID]
    macro_factor: str
    target_metric: str
    beta: Decimal
    notes: Optional[str] = None
    source: str
    created_at: datetime
    updated_at: datetime


class ElasticityUpsert(BaseModel):
    scenario_id: Optional[PyUUID] = None
    company_id: Optional[PyUUID] = None
    macro_factor: MacroFactor
    target_metric: TargetMetric
    beta: Decimal = Field(..., description="elasticity coefficient, typically -2.0..+2.0")
    notes: Optional[str] = None


class ProjectEffectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: PyUUID
    project_id: PyUUID
    effective_year: int
    target_metric: str
    delta_value_uzs_mln: Optional[Decimal] = None
    delta_pct: Optional[Decimal] = None
    probability_pct: Decimal
    confidence: str
    notes: Optional[str] = None
    extra: Optional[dict] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProjectEffectUpsert(BaseModel):
    project_id: PyUUID
    effective_year: int = Field(..., ge=2020, le=2050)
    target_metric: TargetMetric
    delta_value_uzs_mln: Optional[Decimal] = None
    delta_pct: Optional[Decimal] = None
    probability_pct: Decimal = Field(default=Decimal("100"), ge=0, le=100)
    confidence: Literal["low", "medium", "high"] = "medium"
    notes: Optional[str] = None
    extra: Optional[dict] = None


class DecompositionComponent(BaseModel):
    """Один элемент декомпозиции прогноза."""
    label_ru: str
    contribution_uzs_mln: Decimal
    contribution_pct: Decimal  # % от прогноза
    kind: Literal["base", "macro", "project", "total"]
    detail: Optional[dict] = None  # доп. инфо (какой фактор, какой проект и т.д.)


class DecompositionResult(BaseModel):
    """Результат декомпозиции прогноза на один год / metric / company."""
    company_id: Optional[PyUUID] = None
    company_name: Optional[str] = None
    target_metric: str
    year: int
    base_value_uzs_mln: Decimal
    forecast_value_uzs_mln: Decimal
    macro_effect_uzs_mln: Decimal
    projects_effect_uzs_mln: Decimal
    components: List[DecompositionComponent]
    explanation: str  # человеческое описание
