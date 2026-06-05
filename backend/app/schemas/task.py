"""Pydantic schemas for Boards and Tasks API."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# =====================================================================
# Boards
# =====================================================================

class BoardBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: Optional[str] = None
    color_hex: Optional[str] = None
    sector_code: Optional[str] = None
    company_id: Optional[UUID] = None
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    is_archived: bool
    sort_order: int

    # Aggregates (filled by endpoint)
    tasks_total: int = 0
    tasks_by_status: dict = Field(default_factory=dict)


class BoardListResponse(BaseModel):
    items: list[BoardBrief]
    total: int


# =====================================================================
# Tasks
# =====================================================================

class TaskBrief(BaseModel):
    """Light task row — used in lists and kanban columns."""
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

    assignee_email: Optional[str] = None
    assignee_name: Optional[str] = None
    assignee_id: Optional[UUID] = None

    due_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    project_id: Optional[UUID] = None
    # Deferred to next year — Phase 13
    linked_year: Optional[int] = None
    linked_task_id: Optional[UUID] = None
    # Reverse carry-over link: year this record was carried FROM (set when another
    # task in an earlier year points here via linked_task_id). Computed, not stored.
    carried_from_year: Optional[int] = None
    current_health: Optional[str] = None        # последний health из status_update
    has_unread_comments: bool = False           # непрочитанный коммент от другого
    is_project: bool = False  # Always False — kept for backwards compat with frontend
    progress_percent: int = 0
    sort_order: int = 0  # ручной порядок в списке (drag-reorder)
    is_overdue: bool = False
    # Binary "результат" — NULL if no result yet; datetime when accepted.
    # UI alert when status='done' AND result_at IS NULL.
    result_at: Optional[datetime] = None
    tags: Optional[list] = None

    # Monolith-specific fields exposed for client-side computeProgress.
    # These are derived from `extra` JSONB. None if not set.
    quarters: Optional[dict] = None     # { q1: {weight,plan,fact}, q2: ..., q3: ..., q4: ... }
    consultant: Optional[str | list] = None
    direction: Optional[str] = None
    direction_meta: Optional[dict] = None

    created_at: datetime
    updated_at: datetime


class TaskDetail(TaskBrief):
    """Full task — adds description, scope, consultants, linked task, monolith-specific fields."""
    description: Optional[str] = None
    scope: Optional[str] = None
    linked_task_id: Optional[UUID] = None
    consultants: list[str] = Field(default_factory=list)
    extra: Optional[dict] = None
    legacy_id: Optional[str] = None
    creator_id: Optional[UUID] = None
    start_date: Optional[date] = None
    completed_at: Optional[datetime] = None

    # Monolith-equivalent extra-extracted fields (also in extra dict)
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None

    # Comments (loaded by _hydrate_detail; wire-format = list of dicts matching frontend Comment interface)
    comments: list[dict] = Field(default_factory=list)


class TaskListResponse(BaseModel):
    items: list[TaskBrief]
    total: int
    by_status: dict = Field(default_factory=dict)
    by_priority: dict = Field(default_factory=dict)
    available_years: list[int] = Field(default_factory=list)


# =====================================================================
# Kanban view (single board with tasks grouped by status)
# =====================================================================

class KanbanColumn(BaseModel):
    status: str           # init | new | active | review | done
    label: str            # Russian label
    color: str            # hex color
    tasks: list[TaskBrief]
    count: int


class BoardKanban(BaseModel):
    board: BoardBrief
    columns: list[KanbanColumn]


# =====================================================================
# Mutations
# =====================================================================

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    num: Optional[str] = Field(None, max_length=64)
    # Status: monolith-equivalent including quarterly/monthly/ongoing
    # quarterly = quarter-based progress (q1..q4); monthly/ongoing excluded from %
    status: str = Field("new", pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$")
    priority: str = Field("medium", pattern="^(high|medium|low)$")
    board_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    direction_id: Optional[UUID] = None
    assignee_email: Optional[str] = Field(None, max_length=255)
    assignee_name: Optional[str] = Field(None, max_length=255)
    assignee_id: Optional[UUID] = None
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    tags: Optional[list] = None
    # Monolith-specific (stored in extra JSONB):
    consultant: Optional[str | list] = None      # Single consultant or list
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None       # {value, currency, note, ...}
    quarters: Optional[dict] = None              # {q1: {weight, plan, fact}, ...}
    direction: Optional[str] = None              # Direction code (when no FK)
    scope: Optional[str] = None
    # Year-transfer (Phase 13)
    linked_year: Optional[int] = None
    linked_task_id: Optional[UUID] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    num: Optional[str] = Field(None, max_length=64)
    status: Optional[str] = Field(None, pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$")
    priority: Optional[str] = Field(None, pattern="^(high|medium|low)$")
    board_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    direction_id: Optional[UUID] = None
    assignee_email: Optional[str] = Field(None, max_length=255)
    assignee_name: Optional[str] = Field(None, max_length=255)
    assignee_id: Optional[UUID] = None
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    sort_order: Optional[int] = None  # ручной порядок (drag-reorder)
    tags: Optional[list] = None
    # Year-transfer (Phase 13) — was missing in update schema, so the
    # carry-over feature only worked on CREATE. Added 2026-05-26.
    linked_year: Optional[int] = None
    linked_task_id: Optional[UUID] = None
    # Monolith-specific
    consultant: Optional[str | list] = None
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None
    quarters: Optional[dict] = None
    direction: Optional[str] = None
    scope: Optional[str] = None
