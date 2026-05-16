"""Pydantic schemas for Boards and Tasks API."""
from datetime import date, datetime
from typing import List, Optional
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
    items: List[BoardBrief]
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
    is_project: bool = False  # Always False — kept for backwards compat with frontend
    progress_percent: int = 0
    is_overdue: bool = False
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
    consultants: List[str] = Field(default_factory=list)
    extra: Optional[dict] = None
    legacy_id: Optional[str] = None
    creator_id: Optional[UUID] = None
    start_date: Optional[date] = None
    completed_at: Optional[datetime] = None

    # Monolith-equivalent extra-extracted fields (also in extra dict)
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None

    # Comments (loaded by _hydrate_detail; wire-format = list of dicts matching frontend Comment interface)
    comments: List[dict] = Field(default_factory=list)


class TaskListResponse(BaseModel):
    items: List[TaskBrief]
    total: int
    by_status: dict = Field(default_factory=dict)
    by_priority: dict = Field(default_factory=dict)
    available_years: List[int] = Field(default_factory=list)


# =====================================================================
# Kanban view (single board with tasks grouped by status)
# =====================================================================

class KanbanColumn(BaseModel):
    status: str           # init | new | active | review | done
    label: str            # Russian label
    color: str            # hex color
    tasks: List[TaskBrief]
    count: int


class BoardKanban(BaseModel):
    board: BoardBrief
    columns: List[KanbanColumn]


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
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    portfolio_year: Optional[int] = None
    progress_percent: Optional[int] = Field(None, ge=0, le=100)
    tags: Optional[list] = None
    # Monolith-specific
    consultant: Optional[str | list] = None
    consultant_comment: Optional[str] = None
    economic_effect: Optional[dict] = None
    quarters: Optional[dict] = None
    direction: Optional[str] = None
    scope: Optional[str] = None
