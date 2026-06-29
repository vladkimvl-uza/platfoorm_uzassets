"""Governance schemas — board composition, committees, attendance.

Critical separation (lessons learned):
  - `governance_data` (table GovernanceData) — structured editable
  - `governance_raw` (table GovernanceRaw) — raw Excel snapshot for AI context
  These two MUST NEVER be conflated. This module deals with `governance_data`.
"""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# =====================================================================
# KPI cards
# =====================================================================

class GovernanceOverviewKpis(BaseModel):
    total_companies: int = 0
    companies_with_data: int = 0

    avg_board_size: Optional[float] = None
    avg_independent_pct: Optional[float] = None       # % independent directors (portfolio avg)
    avg_women_pct: Optional[float] = None             # % women directors
    avg_foreign_pct: Optional[float] = None           # % foreign directors
    avg_attendance_pct: Optional[float] = None
    avg_meetings_per_year: Optional[float] = None

    committees_audit_count: int = 0                    # # companies with audit committee
    committees_remuneration_count: int = 0
    committees_nomination_count: int = 0
    committees_strategy_count: int = 0


# =====================================================================
# Diversity stat (for visual block)
# =====================================================================

class DiversityStat(BaseModel):
    label: str
    color: str
    pct: float
    count: int


# =====================================================================
# Company score
# =====================================================================

class GovernanceCompanyScore(BaseModel):
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None
    company_abbr: Optional[str] = None          # legacy short code (NGMK, AGMK, …)
    sector_code: Optional[str] = None
    sector_color: Optional[str] = None          # convenience: prefilled sector colour
    year: Optional[int] = None

    board_size: Optional[int] = None
    independent_count: Optional[int] = None
    women_count: Optional[int] = None
    foreign_count: Optional[int] = None
    vacant_seats: Optional[int] = None          # legacy: vacant
    exec_count: Optional[int] = None            # legacy: exec
    nonexec_count: Optional[int] = None         # legacy: nonexec

    independent_pct: Optional[float] = None
    women_pct: Optional[float] = None
    foreign_pct: Optional[float] = None

    committees_count: int = 0
    has_all_4_committees: bool = False
    has_audit_committee: Optional[bool] = None
    has_remuneration_committee: Optional[bool] = None
    has_nomination_committee: Optional[bool] = None
    has_strategy_committee: Optional[bool] = None
    # Legacy-extended committees (stored in GovernanceData.payload):
    has_anticorr_committee: Optional[bool] = None
    has_procurement_committee: Optional[bool] = None
    has_esg_committee: Optional[bool] = None
    has_dno_insurance: Optional[bool] = None
    has_induction_program: Optional[bool] = None

    meetings_per_year: Optional[int] = None
    attendance_pct: Optional[int] = None

    governance_score: Optional[float] = None    # 0..100 composite score (computed)
    governance_score_1200: Optional[int] = None # legacy raw score (0..1200) from payload
    rank: int = 0

    age_avg: Optional[int] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None


# =====================================================================
# Board member
# =====================================================================

class BoardMemberBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    full_name: str
    position: Optional[str] = None
    role_type: Optional[str] = None
    is_independent: Optional[bool] = None
    is_woman: Optional[bool] = None
    is_foreign: Optional[bool] = None
    appointed_date: Optional[date] = None
    term_end_date: Optional[date] = None
    bio: Optional[str] = None


class BoardMemberCreate(BaseModel):
    company_id: UUID
    full_name: str = Field(..., min_length=1, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    role_type: Optional[str] = Field(None, pattern="^(chairman|independent|state_rep)$")
    is_independent: Optional[bool] = None
    is_woman: Optional[bool] = None
    is_foreign: Optional[bool] = None
    appointed_date: Optional[date] = None
    term_end_date: Optional[date] = None
    bio: Optional[str] = None


class BoardMemberUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    position: Optional[str] = Field(None, max_length=255)
    role_type: Optional[str] = Field(None, pattern="^(chairman|independent|state_rep)$")
    is_independent: Optional[bool] = None
    is_woman: Optional[bool] = None
    is_foreign: Optional[bool] = None
    appointed_date: Optional[date] = None
    term_end_date: Optional[date] = None
    bio: Optional[str] = None


# =====================================================================
# Governance data (editable)
# =====================================================================

class GovernanceDataEdit(BaseModel):
    company_id: UUID
    year: int = Field(..., ge=2000, le=2100)

    board_size: Optional[int] = Field(None, ge=0, le=50)
    independent_directors_count: Optional[int] = Field(None, ge=0, le=50)
    women_directors_count: Optional[int] = Field(None, ge=0, le=50)
    foreign_directors_count: Optional[int] = Field(None, ge=0, le=50)
    avg_age: Optional[int] = Field(None, ge=18, le=120)

    has_audit_committee: Optional[bool] = None
    has_remuneration_committee: Optional[bool] = None
    has_nomination_committee: Optional[bool] = None
    has_strategy_committee: Optional[bool] = None
    # Расширенные комитеты/практики (как на дашборде) — хранятся в payload.
    has_anticorr_committee: Optional[bool] = None
    has_procurement_committee: Optional[bool] = None
    has_esg_committee: Optional[bool] = None
    has_dno_insurance: Optional[bool] = None
    has_induction_program: Optional[bool] = None

    meetings_per_year: Optional[int] = Field(None, ge=0, le=200)
    avg_attendance_pct: Optional[int] = Field(None, ge=0, le=100)

    payload: Optional[dict] = None
    notes: Optional[str] = None


class GovernanceDataBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    year: int
    board_size: Optional[int] = None
    independent_directors_count: Optional[int] = None
    women_directors_count: Optional[int] = None
    foreign_directors_count: Optional[int] = None
    avg_age: Optional[int] = None
    has_audit_committee: Optional[bool] = None
    has_remuneration_committee: Optional[bool] = None
    has_nomination_committee: Optional[bool] = None
    has_strategy_committee: Optional[bool] = None
    # Расширенные комитеты (хранятся в GovernanceData.payload, заполняются в
    # data_to_brief) — иначе detail отдаёт неполный набор комитетов.
    has_anticorr_committee: Optional[bool] = None
    has_procurement_committee: Optional[bool] = None
    has_esg_committee: Optional[bool] = None
    has_dno_insurance: Optional[bool] = None
    has_induction_program: Optional[bool] = None
    meetings_per_year: Optional[int] = None
    avg_attendance_pct: Optional[int] = None
    notes: Optional[str] = None
    updated_at: datetime


# =====================================================================
# Company detail (drill view)
# =====================================================================

class GovernanceCompanyDetail(BaseModel):
    company_id: UUID
    company_code: str
    company_name: Optional[str] = None
    sector_code: Optional[str] = None
    year: int

    data: Optional[GovernanceDataBrief] = None
    board_members: list[BoardMemberBrief] = Field(default_factory=list)

    score: Optional[float] = None
    independent_pct: Optional[float] = None
    women_pct: Optional[float] = None
    foreign_pct: Optional[float] = None

    available_years: list[int] = Field(default_factory=list)


# =====================================================================
# Overview response
# =====================================================================

class GovernanceOverviewResponse(BaseModel):
    year: Optional[int] = None
    sector_code: Optional[str] = None

    kpis: GovernanceOverviewKpis
    diversity_split: list[DiversityStat] = Field(default_factory=list)
    rankings: list[GovernanceCompanyScore] = Field(default_factory=list)

    available_years: list[int] = Field(default_factory=list)
    sectors: list[dict] = Field(default_factory=list)

    generated_at: datetime


# =====================================================================
# Committee meetings — КОЛИЧЕСТВО заседаний НС/комитетов по периодам
# =====================================================================

# Поля-счётчики, доступные для редактирования (whitelist для PUT).
COMMITTEE_MEETING_FIELDS: tuple[str, ...] = (
    "sb_meetings",
    "sb_decisions",
    "audit_mtg",
    "strategy_mtg",
    "nomrem_mtg",
    "anticorr_mtg",
)


class CommitteeMeetingPeriod(BaseModel):
    year: int
    quarter: Optional[int] = None     # None = годовой/полный период; 1..4 = квартал
    label: str                        # "2025" | "2026 · Q1"


class CommitteeMeetingCell(BaseModel):
    sb_meetings: Optional[int] = None
    sb_decisions: Optional[int] = None
    audit_mtg: Optional[int] = None
    strategy_mtg: Optional[int] = None
    nomrem_mtg: Optional[int] = None
    anticorr_mtg: Optional[int] = None


class CommitteeMeetingCompanyRow(BaseModel):
    company_id: UUID
    name: Optional[str] = None
    name_short: Optional[str] = None
    sector_code: Optional[str] = None
    # ключ ячейки: "<year>:<quarter|0>" → значения за период
    cells: dict[str, CommitteeMeetingCell] = Field(default_factory=dict)


class CommitteeMeetingsResponse(BaseModel):
    periods: list[CommitteeMeetingPeriod] = Field(default_factory=list)
    companies: list[CommitteeMeetingCompanyRow] = Field(default_factory=list)


class CommitteeMeetingUpsert(BaseModel):
    company_id: UUID
    year: int = Field(..., ge=2000, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)   # None = годовой период
    field: str = Field(..., min_length=1, max_length=32)
    value: Optional[int] = Field(None, ge=0, le=100000)


class CommitteeMeetingUpsertResult(BaseModel):
    company_id: UUID
    year: int
    quarter: Optional[int] = None
    cell: CommitteeMeetingCell


class CommitteeMeetingPeriodCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)


class CommitteeMeetingPeriodCreateResult(BaseModel):
    ok: bool = True
    period: CommitteeMeetingPeriod
