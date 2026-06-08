"""Calendar — авто-агрегация дедлайнов проектов/задач (read-only) + iCal-фид.

Ничего не хранит: события выводятся из projects/tasks.due_date, scoped по
доступам. Используется per-company вкладкой, глобальным разделом и iCal-подпиской.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/calendar", tags=["calendar"])


async def _query_deadlines(
    db: AsyncSession,
    *,
    scope_ids: Optional[list[str]],
    company_id: Optional[str],
    d_from: date,
    d_to: date,
) -> list[dict]:
    events: list[dict] = []
    for etype, tbl in (("project", "projects"), ("task", "tasks")):
        conds = ["e.due_date IS NOT NULL",
                 "e.due_date::date >= :dfrom",
                 "e.due_date::date <= :dto"]
        params: dict = {"dfrom": d_from, "dto": d_to}
        if company_id:
            conds.append("e.company_id::text = :cid")
            params["cid"] = company_id
        elif scope_ids is not None:
            conds.append("e.company_id::text = ANY(:scope)")
            params["scope"] = scope_ids
        sql = (
            "SELECT e.id::text, e.num, e.title, e.status, e.due_date, e.company_id::text, "
            "COALESCE(c.name_ru, c.name_short, c.code) AS company_name "
            f"FROM {tbl} e LEFT JOIN companies c ON c.id = e.company_id WHERE "
            + " AND ".join(conds)
        )
        rows = (await db.execute(text(sql), params)).all()
        ids = [r[0] for r in rows]
        hmap: dict[str, Optional[str]] = {}
        if ids:
            hr = await db.execute(
                text(
                    "SELECT DISTINCT ON (entity_id) entity_id, health FROM status_update "
                    "WHERE entity_type = :et AND entity_id = ANY(:ids) "
                    "ORDER BY entity_id, created_at DESC"
                ),
                {"et": etype, "ids": ids},
            )
            hmap = {h[0]: h[1] for h in hr.all()}
        for r in rows:
            events.append({
                "entity_type": etype,
                "entity_id": r[0],
                "num": r[1],
                "title": r[2],
                "status": r[3],
                "due_date": r[4].isoformat() if r[4] else None,
                "company_id": r[5],
                "company_name": r[6],
                "current_health": hmap.get(r[0]),
            })
    return events


@router.get("/events")
async def calendar_events(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Дедлайн-события в диапазоне [from, to] (YYYY-MM-DD). company_id опционален
    (без него — все доступные компании = глобальный календарь)."""
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")
    scope = await allowed_company_ids(db, user)
    scope_ids = [str(x) for x in scope] if scope is not None else None
    if scope_ids is not None and len(scope_ids) == 0:
        return []
    if company_id and scope_ids is not None and company_id not in scope_ids:
        return []
    try:
        d_from = date.fromisoformat(from_[:10])
        d_to = date.fromisoformat(to[:10])
    except ValueError:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid date")
    return await _query_deadlines(db, scope_ids=scope_ids, company_id=company_id, d_from=d_from, d_to=d_to)


# ─── iCal-подписка (Outlook/Google/Apple) ─────────────────────────

@router.post("/ical-token")
async def get_ical_token(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Вернуть (создав при необходимости) персональный токен iCal-подписки.
    Фронт строит абсолютный URL: {origin}/api/calendar/ical/{token}.ics"""
    u = await db.get(User, user.id)
    if u is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "user not found")
    if not getattr(u, "ical_token", None):
        u.ical_token = secrets.token_urlsafe(24)
        await db.commit()
    return {"token": u.ical_token, "path": f"/api/calendar/ical/{u.ical_token}.ics"}


def _ics_escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@router.get("/ical/{token}.ics")
async def ical_feed(token: str, db: AsyncSession = Depends(get_db)):
    """Read-only iCal-фид дедлайнов пользователя (по токену, без auth-заголовка —
    для внешних календарных клиентов)."""
    r = await db.execute(text("SELECT id FROM users WHERE ical_token = :t"), {"t": token})
    uid = r.scalar_one_or_none()
    if uid is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "not found")
    u = await db.get(User, uid)
    scope = await allowed_company_ids(db, u)
    scope_ids = [str(x) for x in scope] if scope is not None else None
    today = datetime.now(timezone.utc).date()
    if scope_ids is not None and len(scope_ids) == 0:
        events = []
    else:
        events = await _query_deadlines(
            db, scope_ids=scope_ids, company_id=None,
            d_from=today - timedelta(days=90), d_to=today + timedelta(days=400),
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//UzAssets//Deadlines//RU",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:UzAssets · Дедлайны",
    ]
    for e in events:
        if not e["due_date"]:
            continue
        d = e["due_date"][:10].replace("-", "")
        kind = "Проект" if e["entity_type"] == "project" else "Задача"
        num = (e["num"] + " ") if e["num"] else ""
        summary = f"{num}{e['title']}" + (f" · {e['company_name']}" if e["company_name"] else "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['entity_type']}-{e['entity_id']}@uzassets",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(kind + ' · статус: ' + (e['status'] or '—'))}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines) + "\r\n"
    return Response(content=body, media_type="text/calendar; charset=utf-8")
