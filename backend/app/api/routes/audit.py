"""Audit log REST endpoints (Pack 9.0).

All routes require permission `audit.view` (owner + admin auto-bypass).
Export route requires `audit.admin`.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.audit import (
    AuditEventDetail,
    AuditEventList,
    AuditEventRead,
    AuditOverviewResponse,
    AuditSecurityFlag,
    AuditStat,
    AuditStatsResponse,
    AuditTimelineBucket,
    AuditTimelineResponse,
    AuditTopModule,
    AuditTopUser,
)
from app.services.audit_service import (
    ACCENT,
    compute_stats,
    detect_security_flags,
    query_events,
    timeline as svc_timeline,
    top_modules,
    top_users,
)
from sqlalchemy import select


router = APIRouter(prefix="/admin/audit", tags=["audit"])


# ─── Serializer helpers ──────────────────────────────────────

def _row_to_brief(r: AuditLog) -> AuditEventRead:
    return AuditEventRead(
        id=r.id,
        created_at=r.created_at,
        actor_id=r.actor_id,
        actor_email=r.actor_email,
        actor_role=r.actor_role,
        action=r.action,
        module=r.module,
        entity_type=r.entity_type,
        entity_id=r.entity_id,
        entity_label=r.entity_label,
        http_method=r.http_method,
        http_path=r.http_path,
        http_status=r.http_status,
        duration_ms=r.duration_ms,
        ip_address=str(r.ip_address) if r.ip_address else None,
        is_critical=r.is_critical,
        has_diff=bool(r.diff),
        has_payload=bool(r.payload),
    )


# ─── Overview: one call → entire page ───────────────────────

@router.get("/overview", response_model=AuditOverviewResponse)
async def overview(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    stats_data = await compute_stats(db, hours=hours)

    stats = AuditStatsResponse(
        period_hours=stats_data["period_hours"],
        events_total=stats_data["events_total"],
        unique_users=stats_data["unique_users"],
        online_users=stats_data["online_users"],
        changes=stats_data["changes"],
        views=stats_data["views"],
        errors=stats_data["errors"],
        critical=stats_data["critical"],
        stats=[
            AuditStat(key="events",   label="События",     value=stats_data["events_total"],
                      delta_pct=stats_data["delta_pct"], sub=f"за {hours}ч", accent=ACCENT["events"]),
            AuditStat(key="users",    label="Пользователей", value=stats_data["unique_users"],
                      sub=f"{stats_data['online_users']} активны сейчас", accent=ACCENT["users"]),
            AuditStat(key="changes",  label="Изменений",   value=stats_data["changes"],
                      sub="CREATE · UPDATE · DELETE", accent=ACCENT["changes"]),
            AuditStat(key="views",    label="Просмотров",  value=stats_data["views"],
                      sub="view & queries", accent=ACCENT["views"]),
            AuditStat(key="errors",   label="Ошибок",      value=stats_data["errors"],
                      sub="4xx · 5xx · timeouts", accent=ACCENT["errors"]),
            AuditStat(key="critical", label="Критичных",   value=stats_data["critical"],
                      sub="security flags", accent=ACCENT["critical"]),
        ],
    )

    tu = await top_users(db, hours=hours, limit=5)
    tm = await top_modules(db, hours=hours)
    flags = await detect_security_flags(db)
    tl_buckets = await svc_timeline(db, hours=hours, bucket="hour")

    recent_rows, _total = await query_events(db, limit=10, offset=0)

    return AuditOverviewResponse(
        stats=stats,
        top_users=[AuditTopUser(**u) for u in tu],
        top_modules=[AuditTopModule(**m) for m in tm],
        security_flags=[AuditSecurityFlag(**f) for f in flags],
        timeline=AuditTimelineResponse(
            bucket="hour",
            buckets=[AuditTimelineBucket(**b) for b in tl_buckets],
        ),
        recent_events=[_row_to_brief(r) for r in recent_rows],
    )


# ─── Events list (paginated, filterable) ─────────────────────

@router.get("/events", response_model=AuditEventList)
async def list_events(
    actor_email: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    hours: Optional[int] = Query(None, ge=1, le=720),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None),
    only_critical: bool = Query(False),
    api_key_id: Optional[UUID] = Query(None, description="Pack 12.4: filter by API key"),
    only_api_key: bool = Query(False, description="Pack 12.4: only entries authed via API key"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    if hours is not None and since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

    rows, total = await query_events(
        db,
        actor_email=actor_email,
        module=module,
        action=action,
        since=since,
        until=until,
        search=search,
        only_critical=only_critical,
        api_key_id=str(api_key_id) if api_key_id else None,
        only_api_key=only_api_key,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return AuditEventList(
        items=[_row_to_brief(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


# ─── Single event detail (with diff + payload) ───────────────

@router.get("/events/{event_id}", response_model=AuditEventDetail)
async def event_detail(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    row = (await db.execute(
        select(AuditLog).where(AuditLog.id == event_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    brief = _row_to_brief(row)
    return AuditEventDetail(
        **brief.model_dump(),
        user_agent=row.user_agent,
        diff=row.diff,
        payload=row.payload,
        meta=row.meta,
        notes=row.notes,
        prev_hash=row.prev_hash,
        entry_hash=row.entry_hash,
    )


# ─── Stats only (for refresh polling) ────────────────────────

@router.get("/stats", response_model=AuditStatsResponse)
async def stats_only(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    s = await compute_stats(db, hours=hours)
    return AuditStatsResponse(
        period_hours=s["period_hours"],
        events_total=s["events_total"],
        unique_users=s["unique_users"],
        online_users=s["online_users"],
        changes=s["changes"],
        views=s["views"],
        errors=s["errors"],
        critical=s["critical"],
        stats=[
            AuditStat(key="events",   label="События",     value=s["events_total"],
                      delta_pct=s["delta_pct"], sub=f"за {hours}ч", accent=ACCENT["events"]),
            AuditStat(key="users",    label="Пользователей", value=s["unique_users"],
                      sub=f"{s['online_users']} активны сейчас", accent=ACCENT["users"]),
            AuditStat(key="changes",  label="Изменений",   value=s["changes"],
                      sub="CREATE · UPDATE · DELETE", accent=ACCENT["changes"]),
            AuditStat(key="views",    label="Просмотров",  value=s["views"],
                      sub="view & queries", accent=ACCENT["views"]),
            AuditStat(key="errors",   label="Ошибок",      value=s["errors"],
                      sub="4xx · 5xx · timeouts", accent=ACCENT["errors"]),
            AuditStat(key="critical", label="Критичных",   value=s["critical"],
                      sub="security flags", accent=ACCENT["critical"]),
        ],
    )


# ─── Timeline (chart data) ───────────────────────────────────

@router.get("/timeline", response_model=AuditTimelineResponse)
async def timeline_endpoint(
    hours: int = Query(24, ge=1, le=720),
    bucket: str = Query("hour", regex="^(hour|day)$"),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.view")),
):
    b = await svc_timeline(db, hours=hours, bucket=bucket)
    return AuditTimelineResponse(bucket=bucket, buckets=[AuditTimelineBucket(**x) for x in b])


# ─── CSV export (admin only) ─────────────────────────────────

@router.get("/export.csv")
async def export_csv(
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("audit.admin")),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows, _ = await query_events(db, since=since, limit=10_000, offset=0)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "created_at", "actor_email", "actor_role", "ip",
        "action", "module", "entity_type", "entity_id", "entity_label",
        "method", "path", "status", "duration_ms", "is_critical",
    ])
    for r in rows:
        writer.writerow([
            str(r.id), r.created_at.isoformat() if r.created_at else "",
            r.actor_email or "", r.actor_role or "",
            str(r.ip_address) if r.ip_address else "",
            r.action, r.module or "",
            r.entity_type or "", r.entity_id or "", r.entity_label or "",
            r.http_method or "", r.http_path or "",
            r.http_status if r.http_status is not None else "",
            r.duration_ms if r.duration_ms is not None else "",
            "1" if r.is_critical else "0",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-{hours}h.csv"},
    )
