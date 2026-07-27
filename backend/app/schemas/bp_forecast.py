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


# ─── Квартальный прогноз текущего года (для «Динамики по кварталам») ──

class BpQuarterProjection(BaseModel):
    """Прогноз одного оставшегося квартала (величина ЗА квартал + коридор)."""
    period: str                       # 'q1'..'q4'
    value: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    co_count: int = 0                 # компаний в сводной проекции (company: 1)


# ─── Черновик плана (генератор «Рассчитать показатели») ──────────────

class BpPlanDraftMetric(BaseModel):
    """Предложение плана по одной вводимой метрике ОФР."""
    key: str
    label: str
    annual: Optional[float] = None    # предлагаемый годовой план
    low: Optional[float] = None
    high: Optional[float] = None
    quarters_ytd: Optional[list[Optional[float]]] = None  # [q1..q4] НАРАСТАЮЩИМ итогом
    method: str = "none"              # cagr|ols|none
    confidence: str = "none"
    note: str = ""


class BpPlanDraft(BaseModel):
    """Черновик плана на target_year из истории фактов. НИЧЕГО не пишет —
    применяется редактором только в пустые ячейки и сохраняется штатно."""
    company_id: UUID
    target_year: int
    base_years: list[int] = []
    metrics: list[BpPlanDraftMetric] = []
    note: str = ""


class BpQuarterOutlook(BaseModel):
    """Прогноз оставшихся кварталов года (движок forecast_quarters на ДЕЛЬТАХ
    «за квартал» — кварталы БП хранятся нарастающим итогом, см. ytd_to_deltas).

    scope='company' — движок на рядах компании; scope='portfolio' — движок по
    КАЖДОЙ компании, сводные проекции = Σ по кварталам позже последнего
    портфельного факта (не искажаемся неполнотой q3/q4-планов у большинства)."""
    year: int
    metric: str
    scope: str                        # 'company' | 'portfolio'
    company_id: Optional[UUID] = None
    co_count: int = 0
    q_plan: list[Optional[float]] = []   # дельты «за квартал» (план), [q1..q4]
    q_fact: list[Optional[float]] = []
    projections: list[BpQuarterProjection] = []
    expected_year: Optional[float] = None
    method: str = "none"              # pace|seasonal|run_rate|plan|actual|mixed|none
    confidence: str = "none"          # high|medium|low|none
    note: str = ""
