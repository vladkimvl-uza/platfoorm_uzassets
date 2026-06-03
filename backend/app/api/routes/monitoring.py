"""Monitoring API — период-агрегация прогресса (Контрольная вышка).

GET /monitoring/timeline/{year}?granularity=month|quarter
    Сравнение исполнения задач по месяцам/кварталам за год.
    План  = задачи с дедлайном (due_date) в периоде.
    Факт  = из них выполнено (status='done').
    % = факт / план.

`completed_at` в данных почти не заполнен (легаси), поэтому ось времени —
по due_date (плановый график), а факт — по текущему статусу. Это даёт
понятную картину «сколько задач периода уже закрыто».
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database import get_db
from app.models.task import Task
from app.models.user import User

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

_MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
           "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
_MONTHS_FULL = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
_QUARTERS = ["I квартал", "II квартал", "III квартал", "IV квартал"]


def _zone(pct: int) -> str:
    if pct >= 100:
        return "done"
    if pct >= 90:
        return "ok"
    if pct >= 75:
        return "warn"
    return "bad"


@router.get("/timeline/{year}")
async def progress_timeline(
    year: int,
    granularity: str = Query("month", pattern="^(month|quarter)$"),
    sector: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    base = and_(
        Task.is_archived.is_(False),
        Task.portfolio_year == year,
        Task.due_date.is_not(None),
    )

    # Группировка по месяцу или кварталу due_date
    bucket = (
        extract("month", Task.due_date) if granularity == "month"
        else extract("quarter", Task.due_date)
    )
    rows = (await db.execute(
        select(
            bucket.label("b"),
            func.count().label("plan"),
            func.count().filter(Task.status == "done").label("done"),
        ).where(base).group_by("b").order_by("b"),
    )).all()

    by_bucket = {int(r._mapping["b"]): r._mapping for r in rows}

    n = 12 if granularity == "month" else 4
    labels = _MONTHS if granularity == "month" else ["I", "II", "III", "IV"]
    labels_full = _MONTHS_FULL if granularity == "month" else _QUARTERS

    periods = []
    for i in range(1, n + 1):
        m = by_bucket.get(i)
        plan = int(m["plan"]) if m else 0
        done = int(m["done"]) if m else 0
        pct = round(done / plan * 100) if plan else 0
        periods.append({
            "key": i,
            "label": labels[i - 1],
            "label_full": labels_full[i - 1],
            "plan": plan,
            "done": done,
            "pct": pct,
            "zone": _zone(pct) if plan else "empty",
        })

    # Итоги за год
    totals = (await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Task.status == "done").label("done"),
        ).where(base),
    )).first()
    total = int(totals._mapping["total"]) if totals else 0
    done_total = int(totals._mapping["done"]) if totals else 0

    # Просрочка: дедлайн прошёл, не done
    today = datetime.now(UTC).date()
    overdue = (await db.execute(
        select(func.count()).where(
            base, Task.due_date < today, Task.status != "done",
        ),
    )).scalar() or 0

    return {
        "year": year,
        "granularity": granularity,
        "total": total,
        "done": done_total,
        "pct": round(done_total / total * 100) if total else 0,
        "overdue": int(overdue),
        "periods": periods,
    }
