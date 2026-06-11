"""
backend/app/schemas/executive_dashboard.py — Pydantic схемы для Executive Dashboard.

Pack 1: Row 0 (topbar) + Row 1 (Исполнение задач) + bottom metrics.
Pack 2: + Row 2 — ratings (4 ring cards + table) + execution chart (bar chart).
Pack 3: + Row 2.5 — Финансы · МСФО.
Pack 4: + Row 3 — Направления · Корпуправление · Стандарты.
Pack 5: + Row 2.55 — Экономический эффект.
        + Row 2.6  — BP-трекер портфеля.
        + Row 2.7  — Налоговый вклад в бюджет.
"""
from __future__ import annotations
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ─────────────────────────── Pack 1 ──────────────────────

class ExecCompanyInSector(BaseModel):
    company_id: UUID
    name: str
    pct: int
    board_id: Optional[UUID] = None
    task_total: int = 0
    task_done: int = 0


class ExecSectorRow(BaseModel):
    id: str
    label: str
    color: str
    companies_total: int
    companies_active: int
    avg_pct: int
    companies: List[ExecCompanyInSector]


class ExecBottomMetrics(BaseModel):
    proj_count: int
    task_count: int
    done_proj: int
    done_tasks: int
    deferred_proj: int
    deferred_tasks: int
    avg_completion: int


class ExecAvailableSector(BaseModel):
    id: str
    label: str
    color: str


# ─────────────────────────── Pack 2 — Ratings ──────────────────────

class ExecRingCard(BaseModel):
    label: str
    rated_count: int
    total: int
    not_covered: int
    accent: str
    score: Optional[int] = None
    delta_2024: int = 0


class ExecRatingCell(BaseModel):
    rating: Optional[str] = None
    outlook: Optional[str] = None
    score: Optional[str] = None
    rated_at: Optional[str] = None
    report_url: Optional[str] = None


class ExecRatingRow(BaseModel):
    company_id: UUID
    name: str
    fitch: Optional[ExecRatingCell] = None
    sp: Optional[ExecRatingCell] = None
    moodys: Optional[ExecRatingCell] = None
    sf: Optional[ExecRatingCell] = None
    sp_esg: Optional[ExecRatingCell] = None
    cdp: Optional[ExecRatingCell] = None


class ExecRatingsBlock(BaseModel):
    ring_cards: List[ExecRingCard]
    rows: List[ExecRatingRow]
    rated_total_unique: int
    overall_total: int


# ─────────────────────────── Pack 2 — Execution chart ──────────────────────

class ExecExecutionRow(BaseModel):
    company_id: UUID
    name: str
    pct: int           # факт: % завершённых задач
    plan_pct: int = 0  # план: % задач, чей дедлайн уже наступил (≤ сегодня)
    sector: str


# ═════════════════════════ Pack 4 — Row 3 ═════════════════════════

class ExecDirectionRow(BaseModel):
    id: str
    label: str
    color: str
    projects_total: int
    projects_done: int
    tasks_total: int
    tasks_done: int
    progress_pct: int


# Pack 7.36 — drill modal schemas for "По направлениям" block

class ExecDirectionDrillProject(BaseModel):
    """Один проект в drill-модалке направления."""
    id: UUID
    title: str
    status: str  # init/new/active/review/done
    due_date: Optional[str] = None  # ISO date "YYYY-MM-DD"
    progress_percent: int = 0
    is_overdue: bool = False
    assignee_name: Optional[str] = None


class ExecDirectionDrillTask(BaseModel):
    """Одна задача в drill-модалке направления."""
    id: UUID
    title: str
    status: str
    due_date: Optional[str] = None
    progress_percent: int = 0
    is_overdue: bool = False
    assignee_name: Optional[str] = None
    priority: str = "medium"


class ExecDirectionDrillCompany(BaseModel):
    """Аггрегация по одной компании в drill-модалке направления."""
    company_id: UUID
    company_name: str
    sector: str  # mining / oilgas / energy / transport / other
    projects_total: int
    projects_done: int
    tasks_total: int
    tasks_done: int
    tasks_overdue: int
    projects: List[ExecDirectionDrillProject]
    tasks: List[ExecDirectionDrillTask]


class ExecDirectionDrillResponse(BaseModel):
    """Ответ для GET /dashboard/executive/directions/{code}."""
    direction_id: str   # code, e.g. "esg"
    direction_label: str
    direction_color: str
    progress_pct: int   # tasks-based, same as ExecDirectionRow
    companies_count: int
    projects_total: int
    projects_done: int
    tasks_total: int
    tasks_done: int
    tasks_overdue: int
    assignees_count: int
    companies: List[ExecDirectionDrillCompany]


class ExecGovernanceCompany(BaseModel):
    company_id: UUID
    name: str
    sector: str
    score: int
    score_pct: int
    board_size: int
    independent_count: int
    women_count: int
    indep_pct: int
    women_pct: int


class ExecGovernanceBlock(BaseModel):
    total_companies: int
    avg_score: int
    top_score: int
    avg_indep_pct: int
    avg_women_pct: int
    top_companies: List[ExecGovernanceCompany]


class ExecStandardsRing(BaseModel):
    done: int
    active: int
    init: int
    not_started: int
    pct: int


class ExecStandardsAttention(BaseModel):
    company_id: UUID
    name: str
    sector: str
    ifrs_status: str
    forensic_status: str
    gaps: List[str]


class ExecStandardsBlock(BaseModel):
    total_companies: int
    ifrs: ExecStandardsRing
    forensic: ExecStandardsRing
    attention_list: List[ExecStandardsAttention]


# ═════════════════════════ Pack 5 — Row 2.55 / 2.6 / 2.7 ═════════════════════════

# ─── Block 1 (Pack 5): Экономический эффект ───
class ExecEEKpi(BaseModel):
    """4 KPI band — Экономический эффект."""
    realized_sum: float       # факт (UZS)
    planned_sum: float        # план (UZS)
    pipeline_sum: float       # план - факт
    conversion_pct: int       # realized / planned * 100
    done_count: int
    active_count: int
    total_count: int
    has_data: bool            # False = empty state


class ExecEEProject(BaseModel):
    """Один проект с экономическим эффектом."""
    project_id: UUID
    title: str
    company_name: str
    sector: str
    direction: Optional[str] = None
    status: str
    planned_value: float
    realized_value: float
    pct_realized: int
    unit: str = "млрд сум"


class ExecEconomicEffectBlock(BaseModel):
    """Полный блок Эконом. эффекта."""
    year: int
    kpi: ExecEEKpi
    top_projects: List[ExecEEProject]


# ─── Block 2 (Pack 5 → Pack 7.27): BP-трекер (Performance Spine 1:1 from legacy) ───
class ExecBPCompanyRow(BaseModel):
    """One company in the Performance Spine."""
    company_id: UUID
    name: str
    sector: str
    plan_value: float                    # plan (or prev_year value in YoY mode)
    fact_value: float                    # fact of selected year
    # Pct of plan/prev — None when ratio is meaningless (signed metric edge cases)
    pct: Optional[float] = None          # As fraction (1.0 = baseline)
    display_pct: Optional[int] = None    # Rounded integer % for display, None when not meaningful
    display_label: Optional[str] = None  # Short label (e.g. '↑ восст.', '↓ убыток', '×3.2')
    display_label_full: Optional[str] = None  # Full label (tooltip)
    delta: Optional[float] = None        # cur - ref (raw, signed)
    cls: str = "warn"                    # 'ok' | 'warn' | 'bad'
    note: Optional[str] = None           # 'recovery' | 'loss' | None


class ExecBPBlock(BaseModel):
    """Full BP-tracker block payload — mirrors legacy _execBPData shape."""
    year: int
    prev_year: int
    metric: str                          # 'revenue' | 'ebitda' | 'profit'
    metric_label: str
    standard: str                        # 'BP' | 'NSBU' | 'IFRS' (source of fact)
    mode: str                            # 'plan-fact' | 'yoy' | 'empty'
    head_sub: str                        # subtitle text
    is_signed_metric: bool = False       # True for profit/ebitda

    # Like-for-like totals used for headline percentage
    plan_total: float = 0                # legacy: sumPlan (raw sum, all rows)
    fact_total: float = 0                # legacy: sumFact

    sum_plan_ll: float = 0               # like-for-like sums (only pairs)
    sum_fact_plan_ll: float = 0
    sum_prev_ll: float = 0
    sum_fact_ll: float = 0

    # Headline number
    overall_pct: Optional[float] = None  # ratio (1.0 = baseline) — None when not meaningful
    prev_overall_pct: Optional[float] = None  # ratio from year-2 vs year-1
    overall_delta: Optional[float] = None     # for signed metrics — absolute delta
    overall_label: Optional[str] = None       # for signed metrics — text label

    # Performance Spine: ALL classified companies (sorted by pct desc by backend)
    rows: List[ExecBPCompanyRow]

    # Counters for footer distribution bar
    on_target: int = 0
    attention: int = 0
    behind: int = 0
    total_count: int = 0
    with_pct_count: int = 0

    available_metrics: List[str] = ["revenue", "ebitda", "profit"]

    # Year-fallback: если за запрошенный год данных нет, показываем последний
    # год с данными (year выше), а requested_year хранит исходно выбранный.
    requested_year: Optional[int] = None


# ─── Block 3 (Pack 5): Налоговый вклад ───
class ExecTaxKpi(BaseModel):
    """Сумма налогов (UZS, текущая шкала)."""
    income_tax: float          # Налог на прибыль (sum, в млрд сум)
    vat: float                 # НДС (revenue × 12%, в млрд сум)
    total: float               # income_tax + vat (в млрд сум)
    yoy_total_pct: Optional[float] = None
    yoy_income_tax_pct: Optional[float] = None
    yoy_vat_pct: Optional[float] = None
    budget_share_pct: Optional[float] = None  # % бюджета РУ
    budget: Optional[float] = None             # годовой бюджет РУ для сравнения (млрд)
    vat_is_estimate: bool = True               # Pack 7.9h: НДС оценочный (revenue×12%)


class ExecTaxTopPayer(BaseModel):
    company_id: UUID
    name: str
    sector: str
    amount: float              # сумма налога+НДС от компании (в млрд сум)
    share_pct: int             # доля от total


class ExecTaxBlock(BaseModel):
    year: int
    prev_year: int
    has_data: bool
    standard: str
    cos_count: int
    missing_companies: List[str] = []  # Pack 7.9h: компании без NSBU PL за год
    kpi: ExecTaxKpi
    top_payers: List[ExecTaxTopPayer]
    requested_year: Optional[int] = None  # year-fallback: исходно выбранный год


# ─────────────────────────── Top-level payload ──────────────────────

class ExecutiveDashboardData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    total_companies: int
    title_main: str = "Программа трансформации государственных предприятий"
    title_sub: str

    # Row 1
    row1_title: str = "Исполнение задач Ожиданий Акционера"
    row1_subtitle: str
    sectors: List[ExecSectorRow]
    bottom_metrics: ExecBottomMetrics

    # Row 2 (Pack 2)
    ratings: Optional[ExecRatingsBlock] = None
    execution_chart: List[ExecExecutionRow] = []
    avg_execution_pct: int = 0

    # Row 3 (Pack 4)
    directions: List[ExecDirectionRow] = []
    governance: Optional[ExecGovernanceBlock] = None
    standards: Optional[ExecStandardsBlock] = None

    # Pack 5: Row 2.55 / 2.6 / 2.7
    economic_effect: Optional[ExecEconomicEffectBlock] = None
    bp_tracker: Optional[ExecBPBlock] = None
    tax_contribution: Optional[ExecTaxBlock] = None

    # Filters state
    available_years: List[int]
    available_sectors: List[ExecAvailableSector]
