"""Proactive attention insights — «N вещей требуют внимания».

Быстрый детерминированный эндпоинт (без LLM): агрегирует высокосигнальные
факты из живой БД с RBAC company-scope. Питает карточку на дашборде, чтобы
руководитель при входе сразу видел, на что смотреть.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/insights", tags=["insights"])

_DONE = "('done','completed','finished','cancelled','archived')"


@router.get("/attention")
async def attention(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    allowed = await allowed_company_ids(db, user)  # None=all, []=none, [...]=scoped
    cids: Optional[list[str]] = (
        [str(c) for c in allowed] if isinstance(allowed, list) else None
    )

    def scope(col: str) -> str:
        if allowed == []:
            return " AND false "
        if cids is None:
            return ""
        return f" AND {col}::text = ANY(:cids) "

    params: dict = {}
    if cids is not None:
        params["cids"] = cids

    async def scalar(sql: str) -> int:
        try:
            r = await db.execute(text(sql), params)
            return int(r.scalar() or 0)
        except Exception:
            return 0

    items: list[dict] = []

    # 1) Просроченные задачи
    overdue = await scalar(
        "SELECT count(*) FROM tasks WHERE is_archived = false "
        f"AND due_date < CURRENT_DATE AND lower(status) NOT IN {_DONE}"
        + scope("company_id")
    )
    if overdue:
        items.append({
            "id": "overdue_tasks", "severity": "critical", "icon": "alert",
            "count": overdue,
            "title": f"{overdue} просроченных задач",
            "detail": "дедлайн прошёл, статус не закрыт",
            "link": "/tasks",
        })

    # 2) Дедлайны на ближайшие 7 дней
    due_soon = await scalar(
        "SELECT count(*) FROM tasks WHERE is_archived = false "
        f"AND due_date >= CURRENT_DATE AND due_date <= CURRENT_DATE + 7 "
        f"AND lower(status) NOT IN {_DONE}"
        + scope("company_id")
    )
    if due_soon:
        items.append({
            "id": "due_soon", "severity": "warning", "icon": "clock",
            "count": due_soon,
            "title": f"{due_soon} дедлайнов на этой неделе",
            "detail": "истекают в ближайшие 7 дней",
            "link": "/tasks",
        })

    # 3) Проекты/задачи в зоне риска (последний статус хода = at_risk/blocked/delayed)
    at_risk = await scalar(
        "SELECT count(*) FROM ("
        " SELECT DISTINCT ON (entity_type, entity_id) health"
        " FROM status_update ORDER BY entity_type, entity_id, created_at DESC"
        ") s WHERE lower(s.health) IN ('at_risk','blocked','delayed')"
    )
    if at_risk:
        items.append({
            "id": "at_risk", "severity": "critical", "icon": "pulse",
            "count": at_risk,
            "title": f"{at_risk} в зоне риска",
            "detail": "статус хода — под угрозой / заблокировано",
            "link": "/tasks",
        })

    # 4) На модерации
    moderation = await scalar(
        "SELECT count(*) FROM moderation_submission WHERE status = 'pending'"
        + scope("target_company_id")
    )
    if moderation:
        items.append({
            "id": "moderation", "severity": "warning", "icon": "shield",
            "count": moderation,
            "title": f"{moderation} на модерации",
            "detail": "ожидают вашего решения",
            "link": "/moderation",
        })

    # Сортировка: critical → warning → info
    rank = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda x: (rank.get(x["severity"], 9), -x["count"]))

    return {
        "items": items,
        "total": len(items),
        "all_clear": len(items) == 0,
    }
