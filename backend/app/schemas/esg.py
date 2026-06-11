"""ESG schemas — overview dashboard, per-company detail, metrics editing.

ESG model:
  - 3 pillars: E (environmental), S (social), G (governance)
  - Per-company per-year per-metric values, with optional target/benchmark
  - Material issues with severity (low/med/high/critical) and status (open/...)
  - Free-text notes tied to company/year/metric
  - Per-company year tracking (which years are actively reported)
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._types import MoneyDecimal

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

class AgencyRatingCell(BaseModel):
    """A single agency rating slot for ESGCompanyScore.ratings_by_agency.

    `rating=None` means the company has no rating from that agency yet.
    """
    agency: str
    rating: Optional[str] = None
    score: Optional[str] = None
    outlook: Optional[str] = None
    rating_date_text: Optional[str] = None
    report_url: Optional[str] = None
    is_recent: bool = False              # updated within current or previous year


class ESGCompanyScore(BaseModel):
    """Per-company ESG snapshot for the rankings table."""
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None
    company_abbr: Optional[str] = None
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None

    e_score: Optional[float] = None     # 0..100 normalized score, E pillar
    s_score: Optional[float] = None
    g_score: Optional[float] = None
    overall_score: Optional[float] = None

    metric_count: int = 0
    issues_open: int = 0
    issues_critical: int = 0

    last_year_reported: Optional[int] = None
    rank: int = 0

    # ── Legacy-style agency ratings (Sustainable Fitch / S&P ESG / CDP / …) ──
    # Per-agency cell. Missing agency means no rating yet.
    ratings_by_agency: list[AgencyRatingCell] = Field(default_factory=list)
    # Composite (0..10) computed from agency ratings — legacy `_esgComposite`.
    composite_esg_score: Optional[float] = None
    has_any_rating: bool = False
    recent_updates_count: int = 0       # # of agency ratings updated recently


class AgencyCoverageStat(BaseModel):
    agency: str
    count: int
    color: str


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
    value: Optional[MoneyDecimal] = None
    unit: Optional[str] = None
    target: Optional[MoneyDecimal] = None
    benchmark: Optional[MoneyDecimal] = None
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
    value: Optional[MoneyDecimal] = None
    unit: Optional[str] = Field(None, max_length=32)
    target: Optional[MoneyDecimal] = None
    benchmark: Optional[MoneyDecimal] = None
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

    metrics_e: list[ESGMetricBrief] = Field(default_factory=list)
    metrics_s: list[ESGMetricBrief] = Field(default_factory=list)
    metrics_g: list[ESGMetricBrief] = Field(default_factory=list)
    issues: list[ESGIssueBrief] = Field(default_factory=list)

    available_years: list[int] = Field(default_factory=list)
    tracked_years: list[int] = Field(default_factory=list)


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

    # ── Legacy-style KPI strip (4 cards) ──
    covered_count: int = 0               # companies with ≥1 agency rating
    coverage_pct: int = 0                # covered/total %
    leader_company_id: Optional[UUID] = None
    leader_company_name: Optional[str] = None
    leader_composite: Optional[float] = None     # 0..10
    leader_rating_letter: Optional[str] = None   # "AA", "BBB-", etc.
    leader_ratings_count: int = 0        # how many agencies rate the leader
    unrated_count: int = 0
    recent_updates_count: int = 0        # # of (co, agency) updates in current+previous year


class RecentRatingUpdate(BaseModel):
    """Legacy `recentUpdates` row: company × agency rating updated recently."""
    company_id: UUID
    company_code: str
    company_name: str
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None
    agency: str
    agency_color: str
    rating: Optional[str] = None
    score: Optional[str] = None
    rating_date_text: Optional[str] = None
    report_url: Optional[str] = None


class SectorBreakdownItem(BaseModel):
    code: str
    label: str
    color: str
    total: int
    covered: int
    coverage_pct: int
    leader_company_id: Optional[UUID] = None
    leader_company_name: Optional[str] = None
    leader_composite: Optional[float] = None


class ESGOverviewResponse(BaseModel):
    year: Optional[int] = None
    sector_code: Optional[str] = None

    kpis: ESGOverviewKpis
    pillars: list[PillarStat] = Field(default_factory=list)
    issue_severity_split: list[IssueSeverityStat] = Field(default_factory=list)
    rankings: list[ESGCompanyScore] = Field(default_factory=list)

    # Legacy-style aggregates:
    agency_coverage: list[AgencyCoverageStat] = Field(default_factory=list)
    sector_breakdown: list[SectorBreakdownItem] = Field(default_factory=list)
    recent_updates: list[RecentRatingUpdate] = Field(default_factory=list)

    available_years: list[int] = Field(default_factory=list)
    sectors: list[dict] = Field(default_factory=list)

    generated_at: datetime
