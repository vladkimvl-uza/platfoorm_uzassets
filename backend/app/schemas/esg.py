"""ESG schemas — overview dashboard, per-company detail, metrics editing.

ESG model:
  - 3 pillars: E (environmental), S (social), G (governance)
  - Per-company per-year per-metric values, with optional target/benchmark
  - Material issues with severity (low/med/high/critical) and status (open/...)
  - Free-text notes tied to company/year/metric
  - Per-company year tracking (which years are actively reported)
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# Pillar aggregates
# =====================================================================

class PillarStat(BaseModel):
    """Per-pillar aggregates across the portfolio."""
    pillar: str                                    # E | S | G
    metric_count: int = 0
    company_count: int = 0
    avg_target_attainment: Optional[float] = None  # avg(value / target) when target present, %
    avg_benchmark_diff: Optional[float] = None     # avg deviation from benchmark, %
    on_target_count: int = 0                       # metrics where value >= target
    behind_count: int = 0                          # metrics where value < target


class IssueSeverityStat(BaseModel):
    severity: str
    label: str
    color: str
    count: int = 0


# =====================================================================
# Company-level rolled-up score
# =====================================================================

class ESGCompanyScore(BaseModel):
    """Per-company ESG snapshot for the rankings table."""
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None
    sector_code: Optional[str] = None

    e_score: Optional[float] = None     # 0..100 normalized score, E pillar
    s_score: Optional[float] = None
    g_score: Optional[float] = None
    overall_score: Optional[float] = None

    metric_count: int = 0
    issues_open: int = 0
    issues_critical: int = 0

    last_year_reported: Optional[int] = None
    rank: int = 0


# =====================================================================
# Issues
# =====================================================================

class ESGIssueBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    pillar: str
    title: str
    description: Optional[str] = None
    severity: Optional[str] = None
    status: str
    created_at: datetime


class ESGIssueCreate(BaseModel):
    company_id: UUID
    pillar: str = Field(..., pattern="^(E|S|G)$")
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    severity: str = Field("med", pattern="^(low|med|high|critical)$")


class ESGIssueUpdate(BaseModel):
    pillar: Optional[str] = Field(None, pattern="^(E|S|G)$")
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    severity: Optional[str] = Field(None, pattern="^(low|med|high|critical)$")
    status: Optional[str] = Field(None, pattern="^(open|in_progress|mitigated|closed)$")


# =====================================================================
# Metrics (the editable rows for a single company)
# =====================================================================

class ESGMetricBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    pillar: str
    metric_code: str
    metric_name: str
    value: Optional[Decimal] = None
    unit: Optional[str] = None
    target: Optional[Decimal] = None
    benchmark: Optional[Decimal] = None
    notes: Optional[str] = None

    target_attainment_pct: Optional[float] = None
    benchmark_diff_pct: Optional[float] = None


class ESGMetricUpsert(BaseModel):
    """Used for both create + update (PUT semantics)."""
    company_id: UUID
    year: int = Field(..., ge=2000, le=2100)
    pillar: str = Field(..., pattern="^(E|S|G)$")
    metric_code: str = Field(..., min_length=1, max_length=64)
    metric_name: str = Field(..., min_length=1, max_length=255)
    value: Optional[Decimal] = None
    unit: Optional[str] = Field(None, max_length=32)
    target: Optional[Decimal] = None
    benchmark: Optional[Decimal] = None
    notes: Optional[str] = None


# =====================================================================
# Company detail (drill view)
# =====================================================================

class ESGCompanyDetail(BaseModel):
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None
    sector_code: Optional[str] = None
    year: int

    e_score: Optional[float] = None
    s_score: Optional[float] = None
    g_score: Optional[float] = None
    overall_score: Optional[float] = None

    metrics_e: List[ESGMetricBrief] = Field(default_factory=list)
    metrics_s: List[ESGMetricBrief] = Field(default_factory=list)
    metrics_g: List[ESGMetricBrief] = Field(default_factory=list)
    issues: List[ESGIssueBrief] = Field(default_factory=list)

    available_years: List[int] = Field(default_factory=list)
    tracked_years: List[int] = Field(default_factory=list)


# =====================================================================
# Overview response (the dashboard root)
# =====================================================================

class ESGOverviewKpis(BaseModel):
    total_companies: int = 0
    companies_with_data: int = 0
    metrics_total: int = 0
    issues_open: int = 0
    issues_critical: int = 0
    avg_overall_score: Optional[float] = None    # 0..100


class ESGOverviewResponse(BaseModel):
    year: Optional[int] = None
    sector_code: Optional[str] = None

    kpis: ESGOverviewKpis
    pillars: List[PillarStat] = Field(default_factory=list)
    issue_severity_split: List[IssueSeverityStat] = Field(default_factory=list)
    rankings: List[ESGCompanyScore] = Field(default_factory=list)

    available_years: List[int] = Field(default_factory=list)
    sectors: List[dict] = Field(default_factory=list)

    generated_at: datetime
