"""Pydantic schemas for Business Plan and KPI dashboards.

Mirror legacy _bpCompute / _kpiComputeSummary output structures so the
frontend can consume responses directly without recomputation.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas._types import MoneyDecimal

PeriodKey = Literal["annual", "q1", "q2", "q3", "q4"]


# ─── Business Plan ────────────────────────────────────────────────

class BpCell(BaseModel):
    """One BP cell — plan/expect/fact for a single (metric, period)."""
    plan: Optional[MoneyDecimal] = None
    expect: Optional[MoneyDecimal] = None
    fact: Optional[MoneyDecimal] = None
    fact_auto: bool = False           # True if `fact` was auto-filled from NSBU


class BpRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    period: PeriodKey
    metric: str
    plan: Optional[MoneyDecimal]
    expect: Optional[MoneyDecimal]
    fact: Optional[MoneyDecimal]


class BpRecordUpsert(BaseModel):
    """Upsert payload for a single BP cell."""
    company_id: UUID
    year: int
    period: PeriodKey
    metric: str
    plan: Optional[MoneyDecimal] = None
    expect: Optional[MoneyDecimal] = None
    fact: Optional[MoneyDecimal] = None


class BpBulkUpsert(BaseModel):
    """Batch upsert (used by editor save)."""
    records: list[BpRecordUpsert]


class BpComputed(BaseModel):
    """Result of `_bpCompute(co, year, period)` — all 22 metrics with auto-calc."""
    company_id: UUID
    year: int
    period: PeriodKey
    metrics: dict[str, BpCell]   # key = BP_METRIC, value = computed cell


# Available companies / years
class BpAvailableCompany(BaseModel):
    company_id: UUID
    company_name_ru: str
    company_code: Optional[str] = None
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    years: list[int]


# Summary (across all companies)
class BpMetricTotal(BaseModel):
    metric: str
    plan: Optional[MoneyDecimal] = None
    expect: Optional[MoneyDecimal] = None
    fact: Optional[MoneyDecimal] = None
    has_plan: bool = False
    has_expect: bool = False
    has_fact: bool = False


class BpCompanyRow(BaseModel):
    company_id: UUID
    company_name_ru: str
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    rev_fact: Optional[MoneyDecimal] = None
    rev_plan: Optional[MoneyDecimal] = None
    pct: Optional[float] = None        # rev_fact / rev_plan * 100


class BpSectorRow(BaseModel):
    sector_code: str
    label: str
    sum_revenue: MoneyDecimal


class BpQuarterRow(BaseModel):
    q: PeriodKey                       # 'q1' | 'q2' | 'q3' | 'q4'
    plan: Optional[MoneyDecimal] = None
    fact: Optional[MoneyDecimal] = None


class BpSummary(BaseModel):
    """Result of `_bpComputeSummary(year, period)` — portfolio-wide aggregation."""
    year: int
    period: PeriodKey
    co_count: int
    totals: list[BpMetricTotal]
    prev_totals: list[BpMetricTotal]   # year-1 annual fact, for YoY
    by_company: list[BpCompanyRow]
    by_sector: list[BpSectorRow]
    by_quarter: list[BpQuarterRow]


# Comments
class BpCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    period: PeriodKey
    body: str
    author_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class BpCommentUpsert(BaseModel):
    company_id: UUID
    year: int
    period: PeriodKey
    body: str


# Attention issues (rules-based)
class BpAttentionIssue(BaseModel):
    severity: Literal["high", "medium", "low"]
    title: str
    value: str
    detail: str


# Achievements
class BpAchievement(BaseModel):
    title: str                         # metric label
    fact: MoneyDecimal
    plan: MoneyDecimal
    pct: float


# ─── KPI ──────────────────────────────────────────────────────────

class KpiQuarter(BaseModel):
    weight: MoneyDecimal = Decimal("0")
    plan: Optional[MoneyDecimal] = None
    fact: Optional[MoneyDecimal] = None


class KpiIndicatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    manager_id: UUID
    sort_order: int
    name: str
    unit: Optional[str]
    direction: str = "up"  # 'up' = больше=лучше | 'down' = меньше=лучше
    weight: MoneyDecimal
    plan_year: Optional[MoneyDecimal]
    fact_year: Optional[MoneyDecimal]
    q1_weight: MoneyDecimal
    q2_weight: MoneyDecimal
    q3_weight: MoneyDecimal
    q4_weight: MoneyDecimal
    q1_plan: Optional[MoneyDecimal]
    q1_fact: Optional[MoneyDecimal]
    q2_plan: Optional[MoneyDecimal]
    q2_fact: Optional[MoneyDecimal]
    q3_plan: Optional[MoneyDecimal]
    q3_fact: Optional[MoneyDecimal]
    q4_plan: Optional[MoneyDecimal]
    q4_fact: Optional[MoneyDecimal]
    notes: Optional[str]
    # Связь с метрикой Бизнес-плана (reference-pull). NULL = свободный KPI.
    bp_metric_key: Optional[str] = None
    # Read-through значения из BP/НСБУ для связанной (annual) строки — заполняются
    # сервисом, НЕ из БД индикатора (его plan_year/fact_year у связанной строки NULL).
    bp_resolved: bool = False                        # план/факт взяты из BP/НСБУ
    bp_source: Optional[str] = None                  # 'nsbu' | 'ytd' | 'bp_plan' | None
    bp_plan_resolved: Optional[MoneyDecimal] = None
    bp_fact_resolved: Optional[MoneyDecimal] = None


class KpiIndicatorUpsert(BaseModel):
    sort_order: int = 0
    name: str
    unit: Optional[str] = None
    direction: str = "up"  # 'up' | 'down'
    weight: MoneyDecimal = Decimal("0")
    plan_year: Optional[MoneyDecimal] = None
    fact_year: Optional[MoneyDecimal] = None
    q1_weight: MoneyDecimal = Decimal("0")
    q2_weight: MoneyDecimal = Decimal("0")
    q3_weight: MoneyDecimal = Decimal("0")
    q4_weight: MoneyDecimal = Decimal("0")
    q1_plan: Optional[MoneyDecimal] = None
    q1_fact: Optional[MoneyDecimal] = None
    q2_plan: Optional[MoneyDecimal] = None
    q2_fact: Optional[MoneyDecimal] = None
    q3_plan: Optional[MoneyDecimal] = None
    q3_fact: Optional[MoneyDecimal] = None
    q4_plan: Optional[MoneyDecimal] = None
    q4_fact: Optional[MoneyDecimal] = None
    notes: Optional[str] = None
    # Связь с метрикой Бизнес-плана (reference-pull). NULL/"" = свободный KPI.
    bp_metric_key: Optional[str] = None


class KpiManagerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    sort_order: int
    title: str
    short_title: Optional[str]
    role: Optional[str]
    indicators: list[KpiIndicatorRead]


class KpiManagerUpsert(BaseModel):
    sort_order: int = 0
    title: str
    short_title: Optional[str] = None
    role: Optional[str] = None
    indicators: list[KpiIndicatorUpsert] = []


class KpiCompanyYearUpsert(BaseModel):
    """Full replacement of all managers for a (company, year) scope."""
    company_id: UUID
    year: int
    managers: list[KpiManagerUpsert]


# Computation result for one indicator (in summary)
KpiStatus = Literal["over", "hit", "risk", "crit", "fail"]


class KpiIndPayload(BaseModel):
    co_id: UUID
    co_name: str
    mgr_idx: int
    mgr: str
    ind_idx: int
    ind_id: UUID
    name: str
    unit: Optional[str]
    weight: MoneyDecimal
    plan: Optional[MoneyDecimal]
    fact: Optional[MoneyDecimal]
    ratio: Optional[float]              # fact/plan (сырое)
    pct: Optional[float]                # clamp[0;150] для отображения/статуса
    pct_raw: Optional[float] = None     # ratio*100 без клэмпа (для прозрачности)
    is_anomaly: bool = False            # pct_raw вне [0;300] — вероятная ошибка данных
    status: Optional[KpiStatus]
    bp_metric_key: Optional[str] = None  # связь с метрикой BP (если финансовый KPI)


class KpiCompanyRow(BaseModel):
    company_id: UUID
    co_name: str
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    count: int                          # scored indicators (weight>0 & ratio есть)
    ind_total: int = 0                  # всего индикаторов у компании (для «N из M»)
    hit: int                            # >= 95
    risk: int                           # 75-95
    crit: int                           # < 75
    pct: float                          # weighted overall %
    low_sample: bool = False            # оценка по слишком малому числу KPI
    weight_skew: bool = False           # один индикатор доминирует над оценкой (>60% веса)


class KpiSectorRow(BaseModel):
    sector_code: str
    label: str
    pct: Optional[float] = None
    count: int = 0
    co_count: int = 0
    low_sample: bool = False            # сектор представлен 1 компанией


class KpiQuarterAgg(BaseModel):
    q: Literal["q1", "q2", "q3", "q4"]
    plan: Optional[float] = None        # 100 if any plan present, else None
    fact: Optional[float] = None        # weighted overall pct


class KpiSummary(BaseModel):
    """Result of `_kpiComputeSummary(year, period)`."""
    year: int
    period: str                         # 'year' | 'q1'..'q4'
    co_count: int
    total_count: int
    overall: Optional[float] = None     # weighted overall %
    low_sample: bool = False            # портфель/выборка слишком малы для уверенности
    over_count: int = 0
    hit_count: int = 0
    risk_count: int = 0
    crit_count: int = 0
    fail_count: int = 0

    distribution: dict[KpiStatus, list[KpiIndPayload]]
    by_company: list[KpiCompanyRow]
    by_sector: list[KpiSectorRow]
    by_quarter: list[KpiQuarterAgg]
    achievements: list[KpiIndPayload]   # top with pct >= 105
    issues: list[KpiIndPayload]         # bottom with pct < 90 and weight >= 5


class KpiAttentionIssue(BaseModel):
    severity: Literal["high", "medium", "low"]
    title: str
    value: str
    detail: str


# Comments
class KpiCommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    period: str
    body: str
    author_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class KpiCommentUpsert(BaseModel):
    company_id: UUID
    year: int
    period: str
    body: str
