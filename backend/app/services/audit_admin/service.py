"""Audit-log admin use-cases (Pack 9.0).

Folder name `audit_admin/` avoids collision with the core
`app.services.audit_service` (stats/timeline/security/query helpers, untouched).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.repositories.audit_repository import AuditRepository
from app.schemas.audit import (
    AuditEventDetail, AuditEventList, AuditEventRead, AuditOverviewResponse,
    AuditSecurityFlag, AuditStat, AuditStatsResponse, AuditTimelineBucket,
    AuditTimelineResponse, AuditTopModule, AuditTopUser,
)
from app.services.audit_service import (
    ACCENT, compute_stats, detect_security_flags, query_events,
    timeline as svc_timeline, top_modules, top_users,
)


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


def _build_stats(s: dict, hours: int) -> AuditStatsResponse:
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
                      delta_pct=s["delta_pct"], sub=f"за {hours}ч",
                      accent=ACCENT["events"]),
            AuditStat(key="users",    label="Пользователей", value=s["unique_users"],
                      sub=f"{s['online_users']} активны сейчас",
                      accent=ACCENT["users"]),
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


@dataclass
class AuditAdminService:
    async def overview(
        self, db: AsyncSession, *, hours: int,
    ) -> AuditOverviewResponse:
        s = await compute_stats(db, hours=hours)
        stats = _build_stats(s, hours)
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

    async def list_events(
        self,
        db: AsyncSession,
        *,
        actor_email: Optional[str] = None,
        module: Optional[str] = None,
        action: Optional[str] = None,
        hours: Optional[int] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        search: Optional[str] = None,
        only_critical: bool = False,
        api_key_id: Optional[UUID] = None,
        only_api_key: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> AuditEventList:
        if hours is not None and since is None:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows, total = await query_events(
            db,
            actor_email=actor_email, module=module, action=action,
            since=since, until=until, search=search,
            only_critical=only_critical,
            api_key_id=str(api_key_id) if api_key_id else None,
            only_api_key=only_api_key,
            limit=per_page, offset=(page - 1) * per_page,
        )
        return AuditEventList(
            items=[_row_to_brief(r) for r in rows],
            total=total,
            page=page,
            per_page=per_page,
        )

    async def event_detail(
        self, event_id: UUID, db: AsyncSession,
    ) -> AuditEventDetail:
        row = await AuditRepository(db).get_event(event_id)
        if row is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Event not found")
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

    async def stats_only(
        self, db: AsyncSession, *, hours: int,
    ) -> AuditStatsResponse:
        s = await compute_stats(db, hours=hours)
        return _build_stats(s, hours)

    async def timeline(
        self, db: AsyncSession, *, hours: int, bucket: str,
    ) -> AuditTimelineResponse:
        b = await svc_timeline(db, hours=hours, bucket=bucket)
        return AuditTimelineResponse(
            bucket=bucket,
            buckets=[AuditTimelineBucket(**x) for x in b],
        )

    async def export_csv(
        self, db: AsyncSession, *, hours: int,
    ) -> StreamingResponse:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows, _ = await query_events(
            db, since=since, limit=10_000, offset=0,
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "id", "created_at", "actor_email", "actor_role", "ip",
            "action", "module", "entity_type", "entity_id", "entity_label",
            "method", "path", "status", "duration_ms", "is_critical",
        ])
        for r in rows:
            writer.writerow([
                str(r.id),
                r.created_at.isoformat() if r.created_at else "",
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
            headers={
                "Content-Disposition": f"attachment; filename=audit-{hours}h.csv"
            },
        )
