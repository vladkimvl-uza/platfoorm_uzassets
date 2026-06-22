"""PMO schemas — P1: расписание / Гантт / зависимости.

Schedule = плоский список баров (проекты + их задачи) с базовым планом,
слипом, флагом критического пути и списком предшественников. Фронт рендерит
таймлайн из этого DTO; критический путь и слип считаются на бэкенде.
"""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleBar(BaseModel):
    """Один бар на таймлайне — проект или задача."""
    id: UUID
    kind: Literal["project", "task"]
    project_id: Optional[UUID] = None     # для задач — родитель (группировка строк)
    title: str
    status: str
    progress_percent: int = 0

    start: Optional[date] = None
    due: Optional[date] = None
    baseline_start: Optional[date] = None
    baseline_due: Optional[date] = None

    is_milestone: bool = False
    assignee_name: Optional[str] = None
    direction: Optional[str] = None

    # Расчётные (бэкенд):
    slip_days: int = 0                    # due − baseline_due (>0 = опоздание)
    on_critical_path: bool = False
    predecessor_ids: list[UUID] = Field(default_factory=list)
    blocked: bool = False                 # есть незавершённый предшественник


class ScheduleResponse(BaseModel):
    company_code: str
    year: Optional[int] = None
    as_of: date
    bars: list[ScheduleBar] = Field(default_factory=list)
    # Сводка портфеля:
    portfolio_slip_days: int = 0          # макс. слип по критическому пути
    forecast_finish: Optional[date] = None
    baseline_finish: Optional[date] = None
    critical_path_ids: list[UUID] = Field(default_factory=list)
    overdue_count: int = 0
    blocked_count: int = 0


# ─── Dependencies ──────────────────────────────────────────────────────

DepType = Literal["FS", "SS", "FF", "SF"]


class DependencyCreate(BaseModel):
    predecessor_id: UUID
    successor_id: UUID
    dep_type: DepType = "FS"
    lag_days: int = 0


class DependencyRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    predecessor_id: UUID
    successor_id: UUID
    dep_type: str
    lag_days: int


# ─── P2: RAID-реестр ───────────────────────────────────────────────────

RaidKind = Literal["risk", "assumption", "issue", "dependency"]
RaidSeverity = Literal["low", "medium", "high", "critical"]
RaidStatus = Literal["open", "mitigating", "closed"]


class RaidItemRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    kind: str
    title: str
    description: Optional[str] = None
    owner_id: Optional[UUID] = None
    owner_name: Optional[str] = None
    severity: str
    probability: int
    impact: int
    score: int
    polarity: str = "threat"
    response_strategy: Optional[str] = None
    status: str
    mitigation: Optional[str] = None
    due_date: Optional[date] = None
    closed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RaidItemCreate(BaseModel):
    kind: RaidKind = "risk"
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    project_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    owner_name: Optional[str] = Field(None, max_length=255)
    severity: RaidSeverity = "medium"
    probability: int = Field(3, ge=1, le=5)
    impact: int = Field(3, ge=1, le=5)
    polarity: Literal["threat", "opportunity"] = "threat"
    response_strategy: Optional[str] = Field(None, max_length=16)
    status: RaidStatus = "open"
    mitigation: Optional[str] = None
    due_date: Optional[date] = None


class RaidItemUpdate(BaseModel):
    kind: Optional[RaidKind] = None
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    project_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    owner_name: Optional[str] = None
    severity: Optional[RaidSeverity] = None
    probability: Optional[int] = Field(None, ge=1, le=5)
    impact: Optional[int] = Field(None, ge=1, le=5)
    polarity: Optional[Literal["threat", "opportunity"]] = None
    response_strategy: Optional[str] = Field(None, max_length=16)
    status: Optional[RaidStatus] = None
    mitigation: Optional[str] = None
    due_date: Optional[date] = None


# ─── PMBOK 7: Стейкхолдеры ─────────────────────────────────────────────

Engagement = Literal["unaware", "resistant", "neutral", "supportive", "leading"]


class StakeholderRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    name: str
    role: Optional[str] = None
    organization: Optional[str] = None
    power: int
    interest: int
    engagement_current: str
    engagement_desired: str
    strategy: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StakeholderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: Optional[str] = Field(None, max_length=255)
    organization: Optional[str] = Field(None, max_length=255)
    project_id: Optional[UUID] = None
    power: int = Field(3, ge=1, le=5)
    interest: int = Field(3, ge=1, le=5)
    engagement_current: Engagement = "neutral"
    engagement_desired: Engagement = "supportive"
    strategy: Optional[str] = None
    contact: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class StakeholderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[str] = Field(None, max_length=255)
    organization: Optional[str] = Field(None, max_length=255)
    project_id: Optional[UUID] = None
    power: Optional[int] = Field(None, ge=1, le=5)
    interest: Optional[int] = Field(None, ge=1, le=5)
    engagement_current: Optional[Engagement] = None
    engagement_desired: Optional[Engagement] = None
    strategy: Optional[str] = None
    contact: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


# ─── PMBOK 7: Журнал — извлечённые уроки + изменения ───────────────────

LessonKind = Literal["success", "problem", "recommendation"]


class LessonRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    kind: str
    title: str
    description: Optional[str] = None
    recommendation: Optional[str] = None
    owner_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LessonCreate(BaseModel):
    kind: LessonKind = "recommendation"
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    recommendation: Optional[str] = None
    owner_name: Optional[str] = Field(None, max_length=255)
    project_id: Optional[UUID] = None


class LessonUpdate(BaseModel):
    kind: Optional[LessonKind] = None
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    recommendation: Optional[str] = None
    owner_name: Optional[str] = None
    project_id: Optional[UUID] = None


ChangeKind = Literal["scope", "schedule", "cost", "quality", "other"]
ChangeStatus = Literal["proposed", "approved", "rejected", "implemented"]


class ChangeRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    kind: str
    title: str
    description: Optional[str] = None
    impact: Optional[str] = None
    requested_by: Optional[str] = None
    status: str
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ChangeCreate(BaseModel):
    kind: ChangeKind = "scope"
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    impact: Optional[str] = None
    requested_by: Optional[str] = Field(None, max_length=255)
    status: ChangeStatus = "proposed"
    decided_by: Optional[str] = Field(None, max_length=255)
    project_id: Optional[UUID] = None


class ChangeUpdate(BaseModel):
    kind: Optional[ChangeKind] = None
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    impact: Optional[str] = None
    requested_by: Optional[str] = None
    status: Optional[ChangeStatus] = None
    decided_by: Optional[str] = None
    project_id: Optional[UUID] = None


# ─── P2: Здоровье (авто-RAG) ───────────────────────────────────────────

class HealthProject(BaseModel):
    project_id: Optional[UUID] = None
    title: str
    rag: str                    # green | amber | red
    progress_percent: int = 0
    slip_days: int = 0
    overdue_count: int = 0
    blocked_count: int = 0
    open_risks: int = 0
    high_risks: int = 0
    reasons: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    company_code: str
    as_of: date
    portfolio_rag: str
    projects: list[HealthProject] = Field(default_factory=list)
    green: int = 0
    amber: int = 0
    red: int = 0
    open_risks: int = 0
    high_risks: int = 0


# ─── P2: Статус-отчёты ─────────────────────────────────────────────────

class StatusReportRead(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    period: Optional[date] = None
    rag: str
    summary: Optional[str] = None
    metrics: Optional[dict] = None
    created_at: datetime


class StatusReportCreate(BaseModel):
    project_id: Optional[UUID] = None   # None = портфельный отчёт
    use_ai: bool = False                # AI-резюме, если ИИ-движок доступен
