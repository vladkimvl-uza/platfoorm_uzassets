"""Audit-log admin use-cases (Pack 9.0).

Folder name `audit_admin/` avoids collision with the core
`app.services.audit_service` (stats/timeline/security/query helpers, untouched).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.repositories.audit_repository import AuditRepository
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
    top_modules,
    top_users,
)
from app.services.audit_service import (
    timeline as svc_timeline,
)


import re as _re

_UUID_RE = _re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


async def _enrich_rows(db: AsyncSession, rows) -> dict:
    """Из http_path резолвим «что за запись» (задача/проект — № + название) и
    «что за компания» (батч-запросами). Для путей с id (/tasks/{id},
    /projects/{id}, /companies/{code|uuid}, /kpi/{company}) — полная картина;
    для body-based (comments/status-updates) — остаётся только модуль.
    Возвращает {row_id: (entity_label, company_name)}."""
    from sqlalchemy import func, select
    from app.models.company import Company
    from app.models.project import Project
    from app.models.task import Task

    parsed: dict = {}
    task_ids: set = set(); proj_ids: set = set(); comp_ids: set = set(); comp_codes: set = set()
    for r in rows:
        p = (r.http_path or "").split("?", 1)[0]
        segs = [s for s in p.split("/") if s and s not in ("api", "v1")]
        info: dict = {}
        for i, s in enumerate(segs):
            nxt = segs[i + 1] if i + 1 < len(segs) else None
            if not nxt:
                continue
            if s == "tasks" and _UUID_RE.fullmatch(nxt):
                info["task"] = nxt; task_ids.add(nxt)
            elif s == "projects" and _UUID_RE.fullmatch(nxt):
                info["project"] = nxt; proj_ids.add(nxt)
            elif s in ("companies", "kpi") and _UUID_RE.fullmatch(nxt):
                info["company_id"] = nxt; comp_ids.add(nxt)
            elif s == "companies" and not _UUID_RE.fullmatch(nxt):
                info["company_code"] = nxt.lower(); comp_codes.add(nxt.lower())
        parsed[str(r.id)] = info

    tasks: dict = {}
    if task_ids:
        for t in (await db.execute(select(Task.id, Task.num, Task.title, Task.company_id).where(Task.id.in_(task_ids)))).all():
            tasks[str(t[0])] = (t[1], t[2], str(t[3]) if t[3] else None)
    projects: dict = {}
    if proj_ids:
        for t in (await db.execute(select(Project.id, Project.num, Project.title, Project.company_id).where(Project.id.in_(proj_ids)))).all():
            projects[str(t[0])] = (t[1], t[2], str(t[3]) if t[3] else None)
    for v in list(tasks.values()) + list(projects.values()):
        if v[2]:
            comp_ids.add(v[2])

    comps_by_id: dict = {}
    if comp_ids:
        for c in (await db.execute(select(Company.id, Company.name_ru, Company.name_short, Company.code).where(Company.id.in_(comp_ids)))).all():
            comps_by_id[str(c[0])] = c[1] or c[2] or c[3]
    comps_by_code: dict = {}
    if comp_codes:
        for c in (await db.execute(select(Company.code, Company.name_ru, Company.name_short).where(func.lower(Company.code).in_(comp_codes)))).all():
            comps_by_code[(c[0] or "").lower()] = c[1] or c[2] or c[0]

    out: dict = {}
    for r in rows:
        info = parsed.get(str(r.id), {})
        label = r.entity_label
        company = None
        if info.get("task") and info["task"] in tasks:
            num, title, cid = tasks[info["task"]]
            label = ((str(num) + " ") if num else "") + (title or "")
            company = comps_by_id.get(cid) if cid else None
        elif info.get("project") and info["project"] in projects:
            num, title, cid = projects[info["project"]]
            label = ((str(num) + " ") if num else "") + (title or "")
            company = comps_by_id.get(cid) if cid else None
        if company is None:
            if info.get("company_id"):
                company = comps_by_id.get(info["company_id"])
            elif info.get("company_code"):
                company = comps_by_code.get(info["company_code"])
        out[str(r.id)] = (label or None, company)
    return out


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
        action_category: Optional[str] = None,
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
            since = datetime.now(UTC) - timedelta(hours=hours)
        rows, total = await query_events(
            db,
            actor_email=actor_email, module=module, action=action,
            action_category=action_category,
            since=since, until=until, search=search,
            only_critical=only_critical,
            api_key_id=str(api_key_id) if api_key_id else None,
            only_api_key=only_api_key,
            limit=per_page, offset=(page - 1) * per_page,
        )
        # Обогащение: «что за запись» + «что за компания» из http_path.
        try:
            enrich = await _enrich_rows(db, rows)
        except Exception:
            enrich = {}
        items = []
        for r in rows:
            b = _row_to_brief(r)
            el, cn = enrich.get(str(r.id), (None, None))
            if el:
                b.entity_label = el
            if cn:
                b.company_name = cn
            items.append(b)
        return AuditEventList(
            items=items,
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
        since = datetime.now(UTC) - timedelta(hours=hours)
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

    async def purge(
        self, db: AsyncSession, *, keep_days: Optional[int],
        actor_id: Optional[str], actor_email: Optional[str],
    ) -> dict:
        """OWNER-only: очистка журнала аудита.

        keep_days=N → удалить записи старше N дней; keep_days=None/0 → удалить ВСЁ.
        После удаления пересобираем HMAC-цепочку оставшихся (иначе verify_chain
        порвётся) и записываем сам факт очистки отдельной audit-записью.
        """
        from sqlalchemy import delete as sa_delete, func, select, text
        from app.core.audit_chain import append_audit_entry, rebuild_chain

        # Сериализуемся с писателями цепочки.
        await db.execute(text("SELECT id FROM audit_chain_lock WHERE id = 1 FOR UPDATE"))

        before = (await db.execute(select(func.count()).select_from(AuditLog))).scalar() or 0

        cutoff_iso = None
        if keep_days and keep_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=keep_days)
            cutoff_iso = cutoff.isoformat()
            await db.execute(sa_delete(AuditLog).where(AuditLog.created_at < cutoff))
        else:
            await db.execute(sa_delete(AuditLog))
        await db.flush()

        remaining = (await db.execute(select(func.count()).select_from(AuditLog))).scalar() or 0
        deleted = before - remaining

        # Пересобрать цепочку оставшихся (re-anchor от GENESIS).
        await rebuild_chain(db)

        # Зафиксировать сам факт очистки (линкуется к новому концу цепочки).
        note = (f"Удалено {deleted} записей старше {keep_days} дн"
                if (keep_days and keep_days > 0)
                else f"Полная очистка журнала: удалено {deleted} записей")
        await append_audit_entry(
            db,
            actor_id=actor_id, actor_email=actor_email,
            action="audit.purge",
            notes=note,
            payload={"deleted": deleted, "keep_days": keep_days, "cutoff": cutoff_iso},
            is_critical=True,
        )
        await db.commit()
        return {"deleted": deleted, "remaining": remaining + 1, "keep_days": keep_days}
