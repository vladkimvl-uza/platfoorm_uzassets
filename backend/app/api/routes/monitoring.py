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
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.security import get_current_user
from app.database import get_db
from app.models.company import Company, Sector
from app.models.progress_snapshot import ProgressSnapshot
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


@router.get("/companies/{year}")
async def companies_timeline(
    year: int,
    granularity: str = Query("quarter", pattern="^(month|quarter)$"),
    metric: str = Query("tasks", pattern="^(tasks|projects)$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Per-company исполнение по периодам — для построчного сравнения A↔B.

    План = записи (задачи/проекты) с дедлайном в периоде, факт = выполнено.
    """
    model = Task if metric == "tasks" else Project
    base = and_(
        model.is_archived.is_(False),
        model.portfolio_year == year,
        model.due_date.is_not(None),
        model.company_id.is_not(None),
    )
    bucket = (
        extract("month", model.due_date) if granularity == "month"
        else extract("quarter", model.due_date)
    )
    rows = (await db.execute(
        select(
            model.company_id.label("cid"),
            bucket.label("b"),
            func.count().label("plan"),
            func.count().filter(model.status == "done").label("done"),
        ).where(base).group_by(model.company_id, "b"),
    )).all()

    agg: dict = {}
    for r in rows:
        agg.setdefault(r._mapping["cid"], {})[int(r._mapping["b"])] = (
            int(r._mapping["plan"]), int(r._mapping["done"]),
        )

    co_rows = (await db.execute(
        select(
            Company.id, Company.code, Company.name_short, Company.name_ru,
            Sector.code.label("sec_code"), Sector.name_ru.label("sec_name"),
            Sector.color_hex.label("sec_color"), Sector.short_badge.label("sec_badge"),
        ).join(Sector, Company.sector_id == Sector.id, isouter=True),
    )).all()

    short, full, n = _labels(granularity)
    companies = []
    for c in co_rows:
        buckets = agg.get(c._mapping["id"])
        if not buckets:
            continue
        periods = []
        for i in range(1, n + 1):
            plan, done = buckets.get(i, (0, 0))
            pct = round(done / plan * 100) if plan else 0
            periods.append({
                "key": i, "label": short[i - 1], "label_full": full[i - 1],
                "plan": plan, "done": done, "pct": pct,
            })
        m = c._mapping
        companies.append({
            "company_id": str(m["id"]),
            "code": m["code"],
            "name": m["name_short"] or m["name_ru"],
            "sector": m["sec_name"] or m["sec_code"] or "—",
            "sector_color": m["sec_color"] or "#888780",
            "badge": m["sec_badge"] or (m["sec_code"] or "")[:4].upper(),
            "periods": periods,
        })
    companies.sort(key=lambda x: x["name"])
    return {"year": year, "granularity": granularity, "metric": metric, "companies": companies}


# ════════════════════════════════════════════════════════════
#   Снимки прогресса (фиксация срезов «с этого дня»)
# ════════════════════════════════════════════════════════════

class SnapshotCreate(BaseModel):
    year: int
    label: Optional[str] = None


async def _entity_totals(db: AsyncSession, model, year: int) -> tuple[int, int, int]:
    """(total, done, overdue) для задач/проектов за год по текущему статусу."""
    base = and_(model.is_archived.is_(False), model.portfolio_year == year)
    row = (await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(model.status == "done").label("done"),
        ).where(base),
    )).first()
    today = datetime.now(UTC).date()
    overdue = (await db.execute(
        select(func.count()).where(
            base, model.due_date.is_not(None), model.due_date < today, model.status != "done",
        ),
    )).scalar() or 0
    return int(row._mapping["total"]), int(row._mapping["done"]), int(overdue)


async def _per_company_counts(db: AsyncSession, model, year: int) -> dict:
    base = and_(model.is_archived.is_(False), model.portfolio_year == year, model.company_id.is_not(None))
    rows = (await db.execute(
        select(
            model.company_id.label("cid"),
            func.count().label("total"),
            func.count().filter(model.status == "done").label("done"),
        ).where(base).group_by(model.company_id),
    )).all()
    return {r._mapping["cid"]: (int(r._mapping["total"]), int(r._mapping["done"])) for r in rows}


@router.post("/snapshot", status_code=201)
async def create_snapshot(
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Зафиксировать срез прогресса портфеля на текущий момент."""
    year = body.year
    t_total, t_done, t_over = await _entity_totals(db, Task, year)
    p_total, p_done, p_over = await _entity_totals(db, Project, year)
    t_by = await _per_company_counts(db, Task, year)
    p_by = await _per_company_counts(db, Project, year)

    co_rows = (await db.execute(
        select(Company.id, Company.code, Company.name_short, Company.name_ru),
    )).all()
    companies = []
    for c in co_rows:
        m = c._mapping
        tt, td = t_by.get(m["id"], (0, 0))
        pt, pd = p_by.get(m["id"], (0, 0))
        if tt == 0 and pt == 0:
            continue
        companies.append({
            "company_id": str(m["id"]), "code": m["code"],
            "name": m["name_short"] or m["name_ru"],
            "tasks_total": tt, "tasks_done": td,
            "projects_total": pt, "projects_done": pd,
        })

    now = datetime.now(UTC)
    label = body.label or f"Срез {now.strftime('%d.%m.%Y %H:%M')}"
    snap = ProgressSnapshot(
        captured_at=now, captured_by=user.id, label=label, year=year, scope="portfolio",
        tasks_total=t_total, tasks_done=t_done,
        projects_total=p_total, projects_done=p_done,
        overdue=t_over + p_over, companies=companies,
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return {
        "id": str(snap.id), "captured_at": snap.captured_at.isoformat(), "label": snap.label,
        "year": snap.year, "tasks_total": t_total, "tasks_done": t_done,
        "projects_total": p_total, "projects_done": p_done, "overdue": t_over + p_over,
        "tasks_pct": round(t_done / t_total * 100) if t_total else 0,
        "companies_count": len(companies),
    }


@router.get("/snapshots")
async def list_snapshots(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    q = select(ProgressSnapshot).order_by(ProgressSnapshot.captured_at.desc()).limit(50)
    if year is not None:
        q = q.where(ProgressSnapshot.year == year)
    rows = (await db.execute(q)).scalars().all()
    return {
        "items": [
            {
                "id": str(s.id), "captured_at": s.captured_at.isoformat(), "label": s.label,
                "year": s.year, "tasks_total": s.tasks_total, "tasks_done": s.tasks_done,
                "projects_total": s.projects_total, "projects_done": s.projects_done,
                "overdue": s.overdue,
                "tasks_pct": round(s.tasks_done / s.tasks_total * 100) if s.tasks_total else 0,
                "projects_pct": round(s.projects_done / s.projects_total * 100) if s.projects_total else 0,
            }
            for s in rows
        ],
        "total": len(rows),
    }
