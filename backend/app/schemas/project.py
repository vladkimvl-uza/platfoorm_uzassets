"""Pydantic schemas for the Projects API."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectBrief(BaseModel):
    """Light project row — used in list views."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    num: Optional[str] = None
    title: str
    status: str
    priority: str

    board_id: Optional[UUID] = None
    board_name: Optional[str] = None
    company_id: Optional[UUID] = None
    company_code: Optional[str] = None
    company_name: Optional[str] = None

    assignee_email: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_id: Optional[UUID] = None

    due_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    # Deferred to next year — Phase 13
    linked_year: Optional[int] = None
    # 2026-05-26: linked_project_id surfaced так же как linked_task_id у tasks —
    # без него frontend «Перенос FY+1» editor получал null и UI казалось не сохранил.
    linked_project_id: Optional[UUID] = None
    progress_percent: int = 0
    sort_order: int = 0  # ручной порядок групп в списке (drag-reorder)
    is_overdue: bool = False
    # Binary "результат" — NULL if no result yet; datetime when accepted.
    # UI alert when status='done' AND result_at IS NULL.
    result_at: Optional[datetime] = None
    tags: Optional[list] = None

    # Aggregated child task counts (filled by endpoint)
    tasks_total: int = 0
    tasks_done: int = 0

    # Monolith-specific (from extra JSONB) — frontend's computeProgress reads these
    quarters: Optional[dict] = None
    consultant: Optional[str | list] = None
    direction: Optional[str] = None
    direction_meta: Optional[dict] = None

    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectBrief):
    description: Optional[str] = None
    scope: Optional[str] = None
    consultants: list[str] = Field(default_factory=list)
    extra: Optional[dict] = None
    legacy_id: Optional[str] = None
    creator_id: Optional[UUID] = None
    start_date: Optional[date] = None
    completed_at: Optional[datetime] = None

    # Monolith-specific (also in extra)
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None

    # Comments (loaded by _hydrate_detail; wire-format = list of dicts matching frontend Comment interface)
    comments: list[dict] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    items: list[ProjectBrief]
    total: int
    by_status: dict = Field(default_factory=dict)
    by_priority: dict = Field(default_factory=dict)
    available_years: list[int] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    num: Optional[str] = Field(None, max_length=64)
    status: str = Field("new", pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$")
    priority: str = Field("medium", pattern="^(high|medium|low)$")
    board_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    direction_id: Optional[UUID] = None
    assignee_email: Optional[str] = Field(None, max_length=255)
    assignee_name: Optional[str] = Field(None, max_length=255)
    assignee_id: Optional[UUID] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    tags: Optional[list] = None
    # Monolith-specific (folded into extra JSONB)
    consultant: Optional[str | list] = None
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None
    quarters: Optional[dict] = None
    direction: Optional[str] = None
    scope: Optional[str] = None
    # Project Editor fields
    ground_type: Optional[str] = Field(None, pattern="^(shareholder|pp|pkm|custom)$")
    ground_number: Optional[str] = Field(None, max_length=64)
    project_type: Optional[str] = Field(None, pattern="^(onetime|recurring)$")
    recurring_period: Optional[str] = Field(None, pattern="^(quarterly|monthly|ongoing)$")
    linked_project_id: Optional[UUID] = None
    consultant_id: Optional[UUID] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    num: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$")
    priority: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    board_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    direction_id: Optional[UUID] = None
    assignee_email: Optional[str] = Field(None, max_length=255)
    assignee_name: Optional[str] = Field(None, max_length=255)
    assignee_id: Optional[UUID] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    sort_order: Optional[int] = None  # ручной порядок (drag-reorder)
    tags: Optional[list] = None
    # Monolith-specific
    consultant: Optional[str | list] = None
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None
    quarters: Optional[dict] = None
    direction: Optional[str] = None
    scope: Optional[str] = None
    # 2026-05-26: Project Editor column-fields добавлены в UPDATE —
    # раньше Pydantic их молча отбрасывал (были только в CREATE) →
    # «Перенос FY+1» и смена ground_type не сохранялись при правке.
    # Не-column поля (ground_number, recurring_period, consultant_id)
    # сюда добавлять НЕЛЬЗЯ — setattr на них упадёт; их надо
    # класть в EXTRA_FIELDS (отдельный фикс на потом).
    ground_type: Optional[str] = Field(None, pattern="^(shareholder|pp|pkm|custom)$")
    project_type: Optional[str] = Field(None, pattern="^(onetime|recurring)$")
    linked_year: Optional[int] = None
    linked_project_id: Optional[UUID] = None
