"""DTO прогноза KPI (детерминированный движок core/forecast).

Зеркалит выход `ForecastResult.to_dict()` + добавляет контекст индикатора
(актуальные план/факт, история годового ряда) для витрины и грудинга ИИ.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ForecastPoint(BaseModel):
    period: str                      # 'q3' | 'q4' | '2027'
    value: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    # Разбивка годового значения по кварталам [q1..q4] (сезонность) — для
    # годовых проекций будущих лет; None для квартальных точек текущего года.
    quarters: Optional[list[Optional[float]]] = None


class ForecastBlock(BaseModel):
    method: str                      # 'pace'|'seasonal'|'run_rate'|'plan'|'actual'|'ols'|'cagr'|'none'
    confidence: str                  # 'high'|'medium'|'low'|'none'
    points_used: int = 0
    note: str = ""
    expected_year: Optional[float] = None
    projections: list[ForecastPoint] = []


class SeriesPoint(BaseModel):
    year: int
    fact: Optional[float] = None
    plan: Optional[float] = None


class IndicatorForecast(BaseModel):
    name: str
    unit: Optional[str] = None
    direction: str = "up"
    weight: float = 0.0
    bp_metric_key: Optional[str] = None
    manager: str = ""
    role: Optional[str] = None
    # актуальный контекст (текущий базовый год)
    plan_year: Optional[float] = None
    fact_year: Optional[float] = None
    q_plan: list[Optional[float]] = []
    q_fact: list[Optional[float]] = []
    # прогнозы
    quarterly: ForecastBlock
    annual: ForecastBlock
    history: list[SeriesPoint] = []   # годовой ряд факта (для графика)


class ManagerForecast(BaseModel):
    title: str
    role: Optional[str] = None
    indicators: list[IndicatorForecast] = []


class CompanyForecast(BaseModel):
    company_id: UUID
    company_code: Optional[str] = None
    company_name: str
    base_year: int
    horizon: int
    future_years: list[int] = []
    managers: list[ManagerForecast] = []
    # сводный прогноз выполнения по компании (взвешенно), годовой ряд
    completion: Optional[ForecastBlock] = None
    completion_history: list[SeriesPoint] = []
    note: str = ""


# ─── Черновик планов KPI (генератор «Рассчитать показатели») ─────────

class KpiPlanDraftIndicator(BaseModel):
    """Предложение плана по одному индикатору target-года."""
    name: str
    manager: str
    linked: bool = False              # bp_metric_key задан → план тянется из БП
    current_plan_year: Optional[float] = None
    proposed_plan_year: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    # Квартальные предложения — СУММЫ ЗА КВАРТАЛ (конвенция q*-полей KPI).
    proposed_q: Optional[list[Optional[float]]] = None
    method: str = "none"              # cagr|ols|none
    confidence: str = "none"
    note: str = ""


class KpiPlanDraft(BaseModel):
    """Черновик планов KPI на target_year из истории фактов (сопоставление
    индикаторов между годами по bp_metric_key/нормализованному имени).
    НИЧЕГО не пишет — применяется редактором в пустые планы + штатный save."""
    company_id: UUID
    target_year: int
    base_years: list[int] = []
    indicators: list[KpiPlanDraftIndicator] = []
    note: str = ""
