"""Pydantic schemas for admin broadcasts (Pack 11.2)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AckMode = Literal["none", "click", "text", "select", "yesno", "file"]
ScheduleMode = Literal["oneshot", "interval", "cron"]
BroadcastTrigger = Literal["schedule", "manual", "resend"]


# ─── Targeting helpers ────────────────────────────────────────

class TargetFilterOp(BaseModel):
    field: str
    op: Literal["=", "!=", ">", ">=", "<", "<="]
    value: Any


class TargetFilterExpr(BaseModel):
    ops: list[TargetFilterOp]
    combine: Literal["AND", "OR"] = "AND"


class ScheduleConfig(BaseModel):
    every_days:   Optional[int] = None
    every_weeks:  Optional[int] = None
    every_months: Optional[int] = None
    weekdays: Optional[list[int]] = None       # 0=Mon ... 6=Sun
    time:    Optional[str] = None              # "HH:MM"
    tz:      Optional[str] = "Asia/Tashkent"
    day_of_month: Optional[int] = None
    cron: Optional[str] = None                 # if mode == cron


# ─── Template ─────────────────────────────────────────────────

class TemplateBase(BaseModel):
    name: str
    is_active: bool = True

    type: str = "announcement"
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    attachments: Optional[list[dict]] = None
    icon: Optional[str] = None
    color: Optional[str] = None

    target_user_ids:    Optional[list[UUID]] = None
    target_group_codes: Optional[list[str]]  = None
    target_role_codes:  Optional[list[str]]  = None
    target_company_ids: Optional[list[UUID]] = None
    target_sector_ids:  Optional[list[UUID]] = None
    target_all: bool = False
    target_filter_expr: Optional[TargetFilterExpr] = None

    ack_mode: AckMode = "none"
    ack_question: Optional[str] = None
    ack_options: Optional[list[str]] = None    # for select
    is_sticky: bool = False
    ack_deadline_hours: Optional[int] = None
    auto_resend_hours: Optional[int] = None
    escalate_to_manager: bool = False
    show_site_banner_on_overdue: bool = False

    schedule_mode: ScheduleMode = "oneshot"
    schedule_config: Optional[ScheduleConfig] = None
    schedule_start_at: Optional[datetime] = None
    schedule_end_at:   Optional[datetime] = None


class TemplateCreate(TemplateBase):
    pass


class TemplateUpdate(TemplateBase):
    pass


class TemplateRead(TemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by_id: UUID
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    total_dispatches: int
    total_recipients_lifetime: int
    total_acks_lifetime: int


class TemplateListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    is_active: bool
    type: str
    priority: str
    title: str
    is_sticky: bool
    ack_mode: AckMode
    schedule_mode: ScheduleMode
    next_run_at: Optional[datetime] = None
    last_run_at: Optional[datetime] = None
    total_dispatches: int
    total_acks_lifetime: int
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    items: list[TemplateListItem]
    total: int


class RecipientPreview(BaseModel):
    """Returned by /preview-recipients before user activates a template."""
    total: int
    sample: list[dict]   # [{id, email, full_name}, ...] up to 20


# ─── Dispatch ─────────────────────────────────────────────────

class DispatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    template_id: UUID
    dispatched_at: datetime
    recipients_count: int
    delivered_count: int
    read_count: int
    acked_count: int
    dispatched_by_id: Optional[UUID] = None
    trigger: BroadcastTrigger
    error: Optional[str] = None


class DispatchListResponse(BaseModel):
    items: list[DispatchRead]
    total: int


# ─── Ack ──────────────────────────────────────────────────────

class AckSubmit(BaseModel):
    response_text:  Optional[str] = None
    response_value: Optional[str] = None
    response_file:  Optional[dict] = None


class AckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    notification_id: UUID
    user_id: UUID
    acknowledged_at: datetime
    response_text:  Optional[str] = None
    response_value: Optional[str] = None
    response_file:  Optional[dict] = None


# ─── Analytics ────────────────────────────────────────────────

class NonResponder(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None


class BroadcastAnalytics(BaseModel):
    template_id: UUID
    template_name: str
    is_active: bool

    dispatches_total: int
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None

    last_recipients: int = 0
    last_delivered: int = 0
    last_read: int = 0
    last_acked: int = 0

    response_distribution: dict[str, int] = Field(default_factory=dict)
    non_responders: list[NonResponder] = Field(default_factory=list)

    history: list[DispatchRead] = Field(default_factory=list)


# ─── Recipient view (notifications enriched with ack data) ────

class StickyNotification(BaseModel):
    """A pending sticky notification for the current user."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    type: str
    priority: str
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    is_sticky: bool
    requires_ack: bool
    ack_mode: Optional[AckMode] = None
    ack_question: Optional[str] = None
    ack_options: Optional[list[str]] = None
    ack_deadline: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    show_site_banner: bool
    broadcast_template_id: Optional[UUID] = None
    source_user_id: Optional[UUID] = None
