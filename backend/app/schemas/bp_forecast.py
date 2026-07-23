"""DTO прогноза Бизнес-плана (детерминированный движок core/forecast).

Прогнозирует финансовые метрики БП (ОФР) по годам + кварталам (сезонность).
Переиспользует ForecastBlock/SeriesPoint из kpi_forecast.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.kpi_forecast import ForecastBlock, SeriesPoint


class BpMetricForecast(BaseModel):
    key: str                          # ключ BP-метрики (revenue, opProfit, profit…)
    label: str
    unit: Optional[str] = None
    direction: str = "up"             # up | down (cost-метрики)
    plan: Optional[float] = None      # план базового года
    expect: Optional[float] = None    # ожидаемое базового года
    fact: Optional[float] = None      # факт базового года
    annual: ForecastBlock             # прогноз по годам (+ квартальная разбивка)
    history: list[SeriesPoint] = []   # годовой ряд факта/плана


class BpCompanyForecast(BaseModel):
    company_id: UUID
    company_code: Optional[str] = None
    company_name: str
    base_year: int
    horizon: int
    future_years: list[int] = []
    metrics: list[BpMetricForecast] = []
    note: str = ""
