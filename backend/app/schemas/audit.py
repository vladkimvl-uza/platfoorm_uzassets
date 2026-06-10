"""Pydantic schemas for /admin/audit/* endpoints (Pack 9.0)."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ─── Event row (used in feed) ────────────────────────────────
class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    actor_id: Optional[UUID] = None
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None

    action: str
    module: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    entity_label: Optional[str] = None
    company_name: Optional[str] = None   # компания, к которой относится действие (resolved)

    http_method: Optional[str] = None
    http_path:   Optional[str] = None
    http_status: Optional[int] = None
    duration_ms: Optional[int] = None

    ip_address: Optional[str] = None
    is_critical: bool = False
    has_diff:    bool = False
    has_payload: bool = False


class AuditEventDetail(AuditEventRead):
    user_agent: Optional[str] = None
    diff:    Optional[dict[str, Any]] = None
    payload: Optional[dict[str, Any]] = None
    meta:    Optional[dict[str, Any]] = None
    notes:   Optional[str] = None
    prev_hash:  Optional[str] = None
    entry_hash: Optional[str] = None


class AuditEventList(BaseModel):
    items: list[AuditEventRead]
    total: int
    page: int
    per_page: int


# ─── Stats / KPI strip ──────────────────────────────────────
class AuditStat(BaseModel):
    key: str
    label: str
    value: int
    delta_pct: Optional[float] = None  # change vs previous period
    sub: Optional[str] = None
    accent: Optional[str] = None       # severity hint: ok / warn / bad / info


class AuditStatsResponse(BaseModel):
    period_hours: int
    events_total: int
    unique_users: int
    online_users: int
    changes:      int
    views:        int
    errors:       int
    critical:     int
    stats: list[AuditStat]


# ─── Top users / modules ─────────────────────────────────────
class AuditTopUser(BaseModel):
    actor_id: Optional[UUID] = None
    email: str
    initials: str
    count: int
    accent: str


class AuditTopModule(BaseModel):
    module: str
    label: str
    count: int


# ─── Security flags ─────────────────────────────────────────
class AuditSecurityFlag(BaseModel):
    id: UUID
    severity: str        # critical | warning | info
    kind: str            # repeated_fails | new_ip | mass_delete | privilege_change
    title: str
    detail: str
    created_at: datetime
    related_user_email: Optional[str] = None
    related_ip: Optional[str] = None
    is_resolved: bool = False


# ─── Timeline (events over time, multi-series) ─────────────
class AuditTimelineBucket(BaseModel):
    ts: datetime
    view:   int = 0
    update: int = 0
    create: int = 0
    delete: int = 0
    error:  int = 0
    login:  int = 0


class AuditTimelineResponse(BaseModel):
    bucket: str          # hour | day
    buckets: list[AuditTimelineBucket]


# ─── Overview (one call → everything for the page) ──────────
class AuditOverviewResponse(BaseModel):
    stats: AuditStatsResponse
    top_users: list[AuditTopUser]
    top_modules: list[AuditTopModule]
    security_flags: list[AuditSecurityFlag]
    timeline: AuditTimelineResponse
    recent_events: list[AuditEventRead]
