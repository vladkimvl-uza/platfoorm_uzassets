"""Pydantic schemas for Business Plan and KPI dashboards.

Mirror monolith _bpCompute / _kpiComputeSummary output structures so the
frontend can consume responses directly without recomputation.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


PeriodKey = Literal["annual", "q1", "q2", "q3", "q4"]


# ─── Business Plan ────────────────────────────────────────────────

class BpCell(BaseModel):
    """One BP cell — plan/expect/fact for a single (metric, period)."""
    plan: Optional[Decimal] = None
    expect: Optional[Decimal] = None
    fact: Optional[Decimal] = None
    fact_auto: bool = False           # True if `fact` was auto-filled from NSBU


class BpRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    period: PeriodKey
    metric: str
    plan: Optional[Decimal]
    expect: Optional[Decimal]
    fact: Optional[Decimal]


class BpRecordUpsert(BaseModel):
    """Upsert payload for a single BP cell."""
    company_id: UUID
    year: int
    period: PeriodKey
    metric: str
    plan: Optional[Decimal] = None
    expect: Optional[Decimal] = None
    fact: Optional[Decimal] = None


class BpBulkUpsert(BaseModel):
    """Batch upsert (used by editor save)."""
    records: List[BpRecordUpsert]


class BpComputed(BaseModel):
    """Result of `_bpCompute(co, year, period)` — all 22 metrics with auto-calc."""
    company_id: UUID
    year: int
    period: PeriodKey
    metrics: Dict[str, BpCell]   # key = BP_METRIC, value = computed cell


# Available companies / years
class BpAvailableCompany(BaseModel):
    company_id: UUID
    company_name_ru: str
    company_code: Optional[str] = None
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    years: List[int]


# Summary (across all companies)
class BpMetricTotal(BaseModel):
    metric: str
    plan: Optional[Decimal] = None
    expect: Optional[Decimal] = None
    fact: Optional[Decimal] = None
    has_plan: bool = False
    has_expect: bool = False
    has_fact: bool = False


class BpCompanyRow(BaseModel):
    company_id: UUID
    company_name_ru: str
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    rev_fact: Optional[Decimal] = None
    rev_plan: Optional[Decimal] = None
    pct: Optional[float] = None        # rev_fact / rev_plan * 100


class BpSectorRow(BaseModel):
    sector_code: str
    label: str
    sum_revenue: Decimal


class BpQuarterRow(BaseModel):
    q: PeriodKey                       # 'q1' | 'q2' | 'q3' | 'q4'
    plan: Optional[Decimal] = None
    fact: Optional[Decimal] = None


class BpSummary(BaseModel):
    """Result of `_bpComputeSummary(year, period)` — portfolio-wide aggregation."""
    year: int
    period: PeriodKey
    co_count: int
    totals: List[BpMetricTotal]
    prev_totals: List[BpMetricTotal]   # year-1 annual fact, for YoY
    by_company: List[BpCompanyRow]
    by_sector: List[BpSectorRow]
    by_quarter: List[BpQuarterRow]


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
    fact: Decimal
    plan: Decimal
    pct: float


# ─── KPI ──────────────────────────────────────────────────────────

class KpiQuarter(BaseModel):
    weight: Decimal = Decimal("0")
    plan: Optional[Decimal] = None
    fact: Optional[Decimal] = None


class KpiIndicatorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    manager_id: UUID
    sort_order: int
    name: str
    unit: Optional[str]
    weight: Decimal
    plan_year: Optional[Decimal]
    fact_year: Optional[Decimal]
    q1_weight: Decimal
    q2_weight: Decimal
    q3_weight: Decimal
    q4_weight: Decimal
    q1_plan: Optional[Decimal]
    q1_fact: Optional[Decimal]
    q2_plan: Optional[Decimal]
    q2_fact: Optional[Decimal]
    q3_plan: Optional[Decimal]
    q3_fact: Optional[Decimal]
    q4_plan: Optional[Decimal]
    q4_fact: Optional[Decimal]
    notes: Optional[str]


class KpiIndicatorUpsert(BaseModel):
    sort_order: int = 0
    name: str
    unit: Optional[str] = None
    weight: Decimal = Decimal("0")
    plan_year: Optional[Decimal] = None
    fact_year: Optional[Decimal] = None
    q1_weight: Decimal = Decimal("0")
    q2_weight: Decimal = Decimal("0")
    q3_weight: Decimal = Decimal("0")
    q4_weight: Decimal = Decimal("0")
    q1_plan: Optional[Decimal] = None
    q1_fact: Optional[Decimal] = None
    q2_plan: Optional[Decimal] = None
    q2_fact: Optional[Decimal] = None
    q3_plan: Optional[Decimal] = None
    q3_fact: Optional[Decimal] = None
    q4_plan: Optional[Decimal] = None
    q4_fact: Optional[Decimal] = None
    notes: Optional[str] = None


class KpiManagerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    sort_order: int
    title: str
    short_title: Optional[str]
    role: Optional[str]
    indicators: List[KpiIndicatorRead]


class KpiManagerUpsert(BaseModel):
    sort_order: int = 0
    title: str
    short_title: Optional[str] = None
    role: Optional[str] = None
    indicators: List[KpiIndicatorUpsert] = []


class KpiCompanyYearUpsert(BaseModel):
    """Full replacement of all managers for a (company, year) scope."""
    company_id: UUID
    year: int
    managers: List[KpiManagerUpsert]


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
    weight: Decimal
    plan: Optional[Decimal]
    fact: Optional[Decimal]
    ratio: Optional[float]              # fact/plan
    pct: Optional[float]                # ratio * 100
    status: Optional[KpiStatus]


class KpiCompanyRow(BaseModel):
    company_id: UUID
    co_name: str
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    count: int                          # total indicators with weight > 0
    hit: int                            # >= 95
    risk: int                           # 75-95
    crit: int                           # < 75
    pct: float                          # weighted overall %


class KpiSectorRow(BaseModel):
    sector_code: str
    label: str
    pct: Optional[float] = None
    count: int = 0
    co_count: int = 0


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
    over_count: int = 0
    hit_count: int = 0
    risk_count: int = 0
    crit_count: int = 0
    fail_count: int = 0

    distribution: Dict[KpiStatus, List[KpiIndPayload]]
    by_company: List[KpiCompanyRow]
    by_sector: List[KpiSectorRow]
    by_quarter: List[KpiQuarterAgg]
    achievements: List[KpiIndPayload]   # top with pct >= 105
    issues: List[KpiIndPayload]         # bottom with pct < 90 and weight >= 5


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
