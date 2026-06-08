"""Pydantic schemas for notifications (Pack 11.0)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["low", "normal", "high", "critical"]


# ─── Notification CRUD ───────────────────────────────────────

class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    type: str
    priority: Priority
    title: str
    body: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    link_url: Optional[str] = None
    source_module: Optional[str] = None
    source_entity_id: Optional[str] = None
    source_user_id: Optional[UUID] = None
    is_read: bool
    read_at: Optional[datetime] = None
    is_archived: bool
    delivered_channels: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int
    page: int
    per_page: int


class UnreadCountResponse(BaseModel):
    count: int
    by_priority: dict[str, int]
    by_type: dict[str, int]
    by_module: dict[str, int] = {}


class NotificationCreate(BaseModel):
    """Used by `/notifications/send` (admin/system endpoint)."""
    recipient_user_id: UUID
    type: str
    priority: Optional[Priority] = None
    title: str
    body: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    link_url: Optional[str] = None
    source_module: Optional[str] = None
    source_entity_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class NotificationBroadcast(BaseModel):
    """Broadcast to many users — by role/group/all."""
    type: str = "system.announcement"
    priority: Priority = "normal"
    title: str
    body: Optional[str] = None
    link_url: Optional[str] = None
    target_role_codes: Optional[list[str]] = None
    target_group_codes: Optional[list[str]] = None
    target_user_ids: Optional[list[UUID]] = None
    target_all: bool = False


class NotificationBulkAction(BaseModel):
    ids: list[UUID]


# ─── Preferences ─────────────────────────────────────────────

DigestMode = Literal["none", "daily", "weekly"]


class NotificationPreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    notification_type: str
    channels: dict[str, bool]
    is_muted: bool
    mute_until: Optional[datetime] = None
    digest_mode: DigestMode


class NotificationPreferenceUpdate(BaseModel):
    notification_type: str
    channels: Optional[dict[str, bool]] = None
    is_muted: Optional[bool] = None
    mute_until: Optional[datetime] = None
    digest_mode: Optional[DigestMode] = None


class NotificationPreferencesBulk(BaseModel):
    preferences: list[NotificationPreferenceUpdate] = Field(default_factory=list)


class NotificationTypeInfo(BaseModel):
    code: str
    label: str
    priority: Priority
    category: str


class NotificationTypesResponse(BaseModel):
    types: list[NotificationTypeInfo]
    categories: list[str]


# ─── Quiet hours (global per-user) ───────────────────────────

class QuietHoursConfig(BaseModel):
    enabled: bool = False
    start_hour: int = Field(22, ge=0, le=23)
    end_hour: int = Field(8, ge=0, le=23)
    timezone: str = "Asia/Tashkent"
    allow_critical: bool = True


# ─── WS payload ──────────────────────────────────────────────

class WSNotification(BaseModel):
    """What's sent over WebSocket to a connected client."""
    event: Literal["notification.new", "notification.read", "notification.unread_count",
                   "notification.archived", "system.ping"] = "notification.new"
    notification: Optional[NotificationRead] = None
    unread_count: Optional[int] = None
    timestamp: datetime
