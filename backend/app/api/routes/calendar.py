"""Calendar — авто-агрегация дедлайнов проектов/задач (read-only).

Ничего не хранит: события выводятся из projects/tasks.due_date, scoped по
доступам. Используется per-company вкладкой и (позже) глобальным разделом.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events")
async def calendar_events(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    company_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Дедлайн-события в диапазоне [from, to] (YYYY-MM-DD)."""
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")
    scope = await allowed_company_ids(db, user)  # None = без ограничения
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
            f"SELECT e.id::text, e.num, e.title, e.status, e.due_date, e.company_id::text "
            f"FROM {tbl} e WHERE " + " AND ".join(conds)
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
                "current_health": hmap.get(r[0]),
            })
    return events
