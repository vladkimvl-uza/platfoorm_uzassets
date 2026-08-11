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
    rating_id: Optional[UUID] = None     # id рейтинга — для inline-редактирования в таблице ESG
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
    planned_count: int = 0               # companies с отметкой «запланировано» (rp) без рейтинга
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


# =====================================================================
# ESG Maturity Cockpit — матрица зрелости 22×6 + EMS
# =====================================================================

class ESGMaturityCellBrief(BaseModel):
    dimension: str
    sub_key: str = ""
    stage: int = 0
    status_text: Optional[str] = None
    value_text: Optional[str] = None
    evidence_url: Optional[str] = None
    due_date: Optional[str] = None


class ESGRatingMini(BaseModel):
    """Компактный ESG-рейтинг для отображения/inline-правки прямо в матрице зрелости."""
    id: Optional[UUID] = None
    agency: str
    rating: Optional[str] = None
    score: Optional[str] = None
    outlook: Optional[str] = None
    report_url: Optional[str] = None
    prev: Optional[str] = None     # предыдущее значение (для динамики «старый → новый»)


class ESGMaturityCompany(BaseModel):
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None
    sector_code: Optional[str] = None
    sector_name: Optional[str] = None
    sector_color: Optional[str] = None
    cells: list[ESGMaturityCellBrief] = Field(default_factory=list)
    dim_stage: dict[str, int] = Field(default_factory=dict)   # D1..D6 → 0..4
    ems: float = 0.0                                          # 0..100
    rating_count: int = 0
    ratings: list[ESGRatingMini] = Field(default_factory=list)   # сами ESG-рейтинги (агентство/значение/ссылка)
    not_needed: bool = False                                  # «не нуждается» → исключена из метрик/статистики
    dim_not_required: list[str] = Field(default_factory=list)    # измерения «не требуется» (D1..D5)
    # Кол-во загруженных документов по этапам ESG: {"D4:2": 3, "D1:iso14001": 1, …}
    # entity_id = "<dim>:<stageIdx>" (climate D4:1..4 / risk D5:1..3 / ISO D1:iso*).
    stage_doc_counts: dict[str, int] = Field(default_factory=dict)


class ESGMaturityBaskets(BaseModel):
    mature: int = 0       # EMS >= 70
    developing: int = 0   # 40..69
    starting: int = 0     # < 40


class ESGMaturityHeatmap(BaseModel):
    year: int
    companies: list[ESGMaturityCompany] = Field(default_factory=list)
    ems_mean: float = 0.0
    ems_median: float = 0.0
    ems_delta_yoy: Optional[float] = None
    baskets: ESGMaturityBaskets = Field(default_factory=ESGMaturityBaskets)
    climate_funnel: list[int] = Field(default_factory=list)   # passed per stage 1..4
    risk_funnel: list[int] = Field(default_factory=list)      # passed per stage 1..3
    iso_full_count: int = 0                                   # компаний со всеми 3 ISO
    rated_count: int = 0
    total_companies: int = 0
    available_years: list[int] = Field(default_factory=list)
    generated_at: datetime


class ESGMaturityCellUpsert(BaseModel):
    company_id: UUID
    year: int = Field(..., ge=2000, le=2100)
    dimension: str = Field(..., max_length=8)
    sub_key: str = Field("", max_length=32)
    stage: Optional[int] = Field(None, ge=0, le=4)
    status_text: Optional[str] = Field(None, max_length=64)
    value_text: Optional[str] = Field(None, max_length=255)
    evidence_url: Optional[str] = None
    due_date: Optional[str] = None
    extra: Optional[dict] = None


# =====================================================================
# ESG SWOT / выводы (портфель + по-компанийно)
# =====================================================================

class ESGSwotItemBrief(BaseModel):
    id: Optional[UUID] = None
    kind: str                       # strength | weakness
    scope: str = "portfolio"        # portfolio | company
    company_id: Optional[UUID] = None
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    title: Optional[str] = None
    body: str
    severity: Optional[str] = None
    order_idx: int = 0
    # Кто добавил вывод: имя/должность/компания — снимки на момент создания
    created_by_name: Optional[str] = None
    created_by_title: Optional[str] = None
    created_by_org: Optional[str] = None
    created_at: Optional[datetime] = None


class ESGSwotResponse(BaseModel):
    portfolio_strengths: list[ESGSwotItemBrief] = Field(default_factory=list)
    portfolio_weaknesses: list[ESGSwotItemBrief] = Field(default_factory=list)
    company_items: list[ESGSwotItemBrief] = Field(default_factory=list)
    generated_at: datetime


class ESGSwotUpsert(BaseModel):
    id: Optional[UUID] = None
    kind: str = Field(..., pattern="^(strength|weakness)$")
    scope: str = Field("portfolio", pattern="^(portfolio|company)$")
    company_id: Optional[UUID] = None
    title: Optional[str] = Field(None, max_length=255)
    body: str = Field(..., min_length=1)
    severity: Optional[str] = None
    order_idx: int = 0


# =====================================================================
# ESG-отчёты по годам (годовая таблица в профиле зрелости, с 2021)
# =====================================================================

class ESGReportBrief(BaseModel):
    id: Optional[UUID] = None
    company_id: UUID
    year: int
    status: Optional[str] = None        # описание/стандарт отчёта
    report_url: Optional[str] = None
    note: Optional[str] = None
    changed_by_name: Optional[str] = None
    updated_at: Optional[datetime] = None


class ESGReportListResponse(BaseModel):
    company_id: UUID
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    items: list[ESGReportBrief] = Field(default_factory=list)
    last_changed_by_name: Optional[str] = None
    last_changed_at: Optional[datetime] = None
    last_changed_year: Optional[int] = None
    generated_at: datetime


class ESGReportUpsert(BaseModel):
    company_id: UUID
    year: int = Field(..., ge=2000, le=2100)
    status: Optional[str] = Field(None, max_length=255)
    report_url: Optional[str] = Field(None, max_length=2000)
    note: Optional[str] = None


# =====================================================================
# ESG-релевантные KPI по компаниям (подтягиваются из модуля KPI по контексту)
# =====================================================================

class ESGKpiBrief(BaseModel):
    name: str
    unit: Optional[str] = None
    manager: Optional[str] = None
    plan: Optional[float] = None
    fact: Optional[float] = None
    pct: Optional[float] = None       # выполнение, % (с учётом direction)
    direction: str = "up"


class ESGKpiCompany(BaseModel):
    company_id: UUID
    company_code: Optional[str] = None
    kpis: list[ESGKpiBrief] = Field(default_factory=list)


class ESGKpiResponse(BaseModel):
    year: int
    items: list[ESGKpiCompany] = Field(default_factory=list)
    generated_at: datetime


class ESGKpiManagerBrief(BaseModel):
    """Существующая «должность» (менеджер KPI) компании за год — для выбора."""
    id: UUID
    title: str
    short_title: Optional[str] = None


class ESGKpiCreate(BaseModel):
    """Ручное добавление ESG-KPI из дашборда → пишется в модуль KPI (sync с /kpi)."""
    company_id: UUID
    year: int = Field(..., ge=2000, le=2100)
    name: str = Field(..., min_length=1, max_length=500)
    unit: Optional[str] = Field(None, max_length=64)
    direction: str = Field("up", pattern="^(up|down)$")
    plan: Optional[float] = None
    fact: Optional[float] = None
    manager_id: Optional[UUID] = None   # существующая должность; None → общий ESG-менеджер
