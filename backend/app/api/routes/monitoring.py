"""Monitoring API — период-агрегация прогресса (Контрольная вышка).

GET /monitoring/timeline/{year}?granularity=month|quarter
    Сравнение исполнения по месяцам/кварталам за год — для ЗАДАЧ и ПРОЕКТОВ:
        План  = записи с дедлайном (due_date) в периоде.
        Факт  = из них выполнено (status='done').
        % = факт / план.
    Плюс активность комментариев по периодам (по created_at).

`completed_at` в данных почти не заполнен (легаси), поэтому ось времени —
по due_date (плановый график), а факт — по текущему статусу.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

_MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
           "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
_MONTHS_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
_QUARTERS = ["I квартал", "II квартал", "III квартал", "IV квартал"]


def _zone(pct: int, has_plan: bool) -> str:
    if not has_plan:
        return "empty"
    if pct >= 100:
        return "done"
    if pct >= 90:
        return "ok"
    if pct >= 75:
        return "warn"
    return "bad"


def _labels(granularity: str):
    if granularity == "month":
        return _MONTHS, _MONTHS_FULL, 12
    return ["I", "II", "III", "IV"], _QUARTERS, 4


async def _aggregate_entity(db: AsyncSession, model, year: int, granularity: str) -> dict:
    """План/факт по периодам для Task или Project (по due_date)."""
    base = and_(
        model.is_archived.is_(False),
        model.portfolio_year == year,
        model.due_date.is_not(None),
    )
    bucket = (
        extract("month", model.due_date) if granularity == "month"
        else extract("quarter", model.due_date)
    )
    rows = (await db.execute(
        select(
            bucket.label("b"),
            func.count().label("plan"),
            func.count().filter(model.status == "done").label("done"),
        ).where(base).group_by("b").order_by("b"),
    )).all()
    by_bucket = {int(r._mapping["b"]): r._mapping for r in rows}

    short, full, n = _labels(granularity)
    periods = []
    for i in range(1, n + 1):
        m = by_bucket.get(i)
        plan = int(m["plan"]) if m else 0
        done = int(m["done"]) if m else 0
        pct = round(done / plan * 100) if plan else 0
        periods.append({
            "key": i, "label": short[i - 1], "label_full": full[i - 1],
            "plan": plan, "done": done, "pct": pct, "zone": _zone(pct, plan > 0),
        })

    totals = (await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(model.status == "done").label("done"),
        ).where(base),
    )).first()
    total = int(totals._mapping["total"]) if totals else 0
    done_total = int(totals._mapping["done"]) if totals else 0

    today = datetime.now(UTC).date()
    overdue = (await db.execute(
        select(func.count()).where(base, model.due_date < today, model.status != "done"),
    )).scalar() or 0

    return {
        "total": total,
        "done": done_total,
        "pct": round(done_total / total * 100) if total else 0,
        "overdue": int(overdue),
        "periods": periods,
    }


async def _aggregate_comments(db: AsyncSession, year: int, granularity: str) -> dict:
    """Активность комментариев (задачи+проекты) по периодам — по created_at."""
    short, full, n = _labels(granularity)
    counts = {i: 0 for i in range(1, n + 1)}
    total = 0
    for cmodel in (TaskComment, ProjectComment):
        bucket = (
            extract("month", cmodel.created_at) if granularity == "month"
            else extract("quarter", cmodel.created_at)
        )
        rows = (await db.execute(
            select(bucket.label("b"), func.count().label("c"))
            .where(extract("year", cmodel.created_at) == year)
            .group_by("b"),
        )).all()
        for r in rows:
            b = int(r._mapping["b"])
            counts[b] = counts.get(b, 0) + int(r._mapping["c"])
            total += int(r._mapping["c"])

    periods = [
        {"key": i, "label": short[i - 1], "label_full": full[i - 1], "count": counts.get(i, 0)}
        for i in range(1, n + 1)
    ]
    return {"total": total, "periods": periods}


@router.get("/timeline/{year}")
async def progress_timeline(
    year: int,
    granularity: str = Query("month", pattern="^(month|quarter)$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    tasks = await _aggregate_entity(db, Task, year, granularity)
    projects = await _aggregate_entity(db, Project, year, granularity)
    comments = await _aggregate_comments(db, year, granularity)
    return {
        "year": year,
        "granularity": granularity,
        "tasks": tasks,
        "projects": projects,
        "comments": comments,
    }
