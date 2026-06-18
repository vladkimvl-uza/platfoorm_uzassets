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

import json
from datetime import UTC, date, datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.core.security import require_permission
from app.database import get_db
from app.models.company import Company, Direction, Sector
from app.models.progress_snapshot import ProgressSnapshot
from app.models.project import Project, ProjectComment
from app.models.task import Task, TaskComment
from app.models.user import User

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Доступ к Execution Summary — по праву monitoring.view, которое admin/OWNER
# выдают через сетку RBAC «Доступ к модулям». super-admin проходит автоматически.
_require_monitoring = require_permission("monitoring.view")

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
    _user: User = Depends(_require_monitoring),
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


# ─────────────────────────────────────────────────────────────────────
# Накопительная динамика: % выполнено от ВСЕГО портфеля к концу периода.
# Прогресс растёт период-к-периоду (дельта = прирост). По задачам.
# ─────────────────────────────────────────────────────────────────────
from datetime import date as _date  # noqa: E402

_Q_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}


def _cum_period_bounds(year: int, granularity: str, key: int) -> tuple:
    """(start, end) даты периода (квартал/месяц) для накопительной динамики."""
    if granularity == "month":
        start = _date(year, key, 1)
        end = (_date(year, key + 1, 1) - timedelta(days=1)) if key < 12 else _date(year, 12, 31)
    else:
        sm = (key - 1) * 3 + 1
        em = _Q_END_MONTH[key]
        start = _date(year, sm, 1)
        end = (_date(year, em + 1, 1) - timedelta(days=1)) if em < 12 else _date(year, 12, 31)
    return start, end


@router.get("/cumulative/{year}")
async def cumulative_dynamics(
    year: int,
    granularity: str = Query("quarter", pattern="^(month|quarter)$"),
    company_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
):
    """Накопительный % выполнения портфеля к концу каждого периода.

    Числитель = задачи, выполненные К концу периода (по дате завершения —
    completed_at, fallback на due_date для legacy); знаменатель = ВСЕ задачи года
    (или одной компании). Прогресс растёт; delta = прирост к прошлому периоду.
    Плюс per-period: завершено в периоде и просрочено.
    """
    base_conds = [Task.is_archived.is_(False), Task.portfolio_year == year]
    if company_id:
        base_conds.append(Task.company_id == company_id)
    total = (await db.execute(select(func.count()).where(and_(*base_conds)))).scalar() or 0

    today = datetime.now(UTC).date()
    short, full, n = _labels(granularity)
    done_date = func.coalesce(func.date(Task.completed_at), Task.due_date)

    # «Выполнено на сейчас» — всего done в скоупе (потолок для текущего/будущих периодов).
    done_now = (await db.execute(select(func.count()).where(
        and_(*base_conds, Task.status == "done"),
    ))).scalar() or 0

    periods = []
    prev_pct: Optional[int] = None
    prev_cum: int = 0
    for i in range(1, n + 1):
        start, end = _cum_period_bounds(year, granularity, i)
        if end >= today:
            # Текущий/будущий период: в будущем ещё ничего не выполнено →
            # накопление = всё сделанное на ДАННЫЙ момент (плоско, без проекции по дедлайнам).
            cum_done = int(done_now)
        else:
            # Завершившийся период: выполнено к его концу (по дате факта / дедлайну-fallback).
            cum_done = int((await db.execute(select(func.count()).where(
                and_(*base_conds, Task.status == "done", done_date.is_not(None), done_date <= end),
            ))).scalar() or 0)
        # Прирост за период выводим из дельты накопления — всегда согласовано с %.
        done_in = max(0, cum_done - prev_cum)
        overdue = (await db.execute(select(func.count()).where(
            and_(*base_conds, Task.status != "done", Task.due_date.is_not(None),
                 Task.due_date >= start, Task.due_date <= end, Task.due_date < today),
        ))).scalar() or 0
        cum_pct = round(cum_done / total * 100) if total else 0
        periods.append({
            "key": i, "label": short[i - 1], "label_full": full[i - 1],
            "cum_done": cum_done, "cum_pct": cum_pct, "total": int(total),
            "done_in_period": done_in, "overdue": int(overdue),
            "delta": (cum_pct - prev_pct) if prev_pct is not None else None,
            "is_future": start > today,
        })
        prev_pct = cum_pct
        prev_cum = cum_done
    return {"year": year, "granularity": granularity, "total": int(total), "periods": periods}


@router.get("/period-tasks/{year}")
async def period_tasks(
    year: int,
    period: int = Query(..., ge=1, le=12),
    granularity: str = Query("quarter", pattern="^(month|quarter)$"),
    company_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
):
    """Детали периода: завершённые и просроченные задачи, по направлениям."""
    start, end = _cum_period_bounds(year, granularity, period)
    today = datetime.now(UTC).date()
    base_conds = [Task.is_archived.is_(False), Task.portfolio_year == year]
    if company_id:
        base_conds.append(Task.company_id == company_id)
    done_date = func.coalesce(func.date(Task.completed_at), Task.due_date)

    async def _rows(extra):
        q = (
            select(Task.num, Task.title, Task.due_date, Company.name_ru, Company.name_short,
                   Direction.name_ru.label("dir"))
            .select_from(Task)
            .outerjoin(Company, Company.id == Task.company_id)
            .outerjoin(Direction, Direction.id == Task.direction_id)
            .where(and_(*base_conds, *extra))
            .order_by(Direction.name_ru.nullslast(), Task.due_date)
            .limit(500)
        )
        out = []
        for r in (await db.execute(q)).all():
            out.append({
                "num": r[0], "title": r[1],
                "due_date": r[2].isoformat() if r[2] else None,
                "company": r[3] or r[4] or "—",
                "direction": r[5] or "Без направления",
            })
        return out

    # Согласовано с накопительной логикой:
    #   будущий период (start > today)  → выполненного ещё нет;
    #   текущий период (start<=today<=end) → всё выполненное с начала периода,
    #       включая задачи с будущим дедлайном, но уже сделанные (без верхней границы);
    #   завершившийся период → выполненное строго внутри [start, end].
    if start > today:
        completed: list = []
    elif end >= today:
        completed = await _rows([Task.status == "done", done_date >= start])
    else:
        completed = await _rows([Task.status == "done", done_date >= start, done_date <= end])
    overdue = await _rows([Task.status != "done", Task.due_date.is_not(None),
                           Task.due_date >= start, Task.due_date <= end, Task.due_date < today])
    return {"completed": completed, "overdue": overdue}


@router.get("/companies/{year}")
async def companies_timeline(
    year: int,
    granularity: str = Query("quarter", pattern="^(month|quarter)$"),
    metric: str = Query("tasks", pattern="^(tasks|projects)$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
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
#   Снимки прогресса + Обзор «Что изменилось»
# ════════════════════════════════════════════════════════════
# Метрика — «Исполнение обязательств»: из задач, чей срок наступил
# (due_date ≤ момент), сколько выполнено. Честная: не проседает от
# будущей работы. Снимок замораживает её; обзор = разница двух снимков
# (или последнего снимка ↔ «сейчас»).

class SnapshotCreate(BaseModel):
    year: int
    label: Optional[str] = None


def _score(due: int, done: int) -> Optional[int]:
    return round(done / due * 100) if due else None


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _period_bounds(year: int, period: Optional[str]) -> Optional[tuple[date, date]]:
    """period: 'all'|None → весь год; 'q1'..'q4'; 'm1'..'m12'."""
    if not period or period == "all":
        return None
    if period.startswith("q"):
        q = int(period[1:])
        return date(year, (q - 1) * 3 + 1, 1), _month_end(year, q * 3)
    if period.startswith("m"):
        m = int(period[1:])
        return date(year, m, 1), _month_end(year, m)
    return None


async def _compute_state(db: AsyncSession, year: int,
                         bounds: Optional[tuple[date, date]] = None) -> dict:
    """Текущее состояние портфеля (опц. в границах периода) + per-company."""
    today = datetime.now(UTC).date()
    due_cond = and_(Task.due_date.is_not(None), Task.due_date <= today)

    def _scope(model):
        c = and_(model.is_archived.is_(False), model.portfolio_year == year)
        if bounds:
            c = and_(c, model.due_date >= bounds[0], model.due_date <= bounds[1])
        return c

    tbase = _scope(Task)
    trow = (await db.execute(select(
        func.count().label("total"),
        func.count().filter(Task.status == "done").label("done"),
        func.count().filter(due_cond).label("due"),
        func.count().filter(and_(due_cond, Task.status == "done")).label("due_done"),
        func.count().filter(and_(Task.due_date < today, Task.status != "done")).label("overdue"),
    ).where(tbase))).first()

    pbase = _scope(Project)
    prow = (await db.execute(select(
        func.count().label("total"),
        func.count().filter(Project.status == "done").label("done"),
        func.count().filter(and_(Project.due_date < today, Project.status != "done")).label("overdue"),
    ).where(pbase))).first()

    # per-company задачи
    rows = (await db.execute(select(
        Task.company_id.label("cid"),
        func.count().filter(due_cond).label("due"),
        func.count().filter(and_(due_cond, Task.status == "done")).label("due_done"),
        func.count().label("total"),
        func.count().filter(Task.status == "done").label("done"),
    ).where(tbase, Task.company_id.is_not(None)).group_by(Task.company_id))).all()
    by_co = {r._mapping["cid"]: r._mapping for r in rows}

    # per-company проекты
    prows = (await db.execute(select(
        Project.company_id.label("cid"),
        func.count().label("total"),
        func.count().filter(Project.status == "done").label("done"),
    ).where(pbase, Project.company_id.is_not(None)).group_by(Project.company_id))).all()
    proj_by_co = {r._mapping["cid"]: (int(r._mapping["total"]), int(r._mapping["done"])) for r in prows}

    # per-company комментарии (обсуждения на задачах+проектах компании)
    cmt_by_co: dict = {}
    tc_rows = (await db.execute(
        select(Task.company_id.label("cid"), func.count().label("c"))
        .join(TaskComment, TaskComment.task_id == Task.id)
        .where(Task.company_id.is_not(None)).group_by(Task.company_id),
    )).all()
    for r in tc_rows:
        cmt_by_co[r._mapping["cid"]] = cmt_by_co.get(r._mapping["cid"], 0) + int(r._mapping["c"])
    pc_rows = (await db.execute(
        select(Project.company_id.label("cid"), func.count().label("c"))
        .join(ProjectComment, ProjectComment.project_id == Project.id)
        .where(Project.company_id.is_not(None)).group_by(Project.company_id),
    )).all()
    for r in pc_rows:
        cmt_by_co[r._mapping["cid"]] = cmt_by_co.get(r._mapping["cid"], 0) + int(r._mapping["c"])

    co_rows = (await db.execute(select(
        Company.id, Company.code, Company.name_short, Company.name_ru,
        Sector.name_ru.label("sec"), Sector.color_hex.label("color"), Sector.short_badge.label("badge"),
    ).join(Sector, Company.sector_id == Sector.id, isouter=True))).all()

    companies = []
    for c in co_rows:
        m = c._mapping
        r = by_co.get(m["id"])
        pt, pd = proj_by_co.get(m["id"], (0, 0))
        if not r and pt == 0:
            continue
        due, due_done = (int(r["due"]), int(r["due_done"])) if r else (0, 0)
        tt, td = (int(r["total"]), int(r["done"])) if r else (0, 0)
        companies.append({
            "company_id": str(m["id"]), "code": m["code"],
            "name": m["name_short"] or m["name_ru"],
            "sector": m["sec"] or "—", "color": m["color"] or "#888780",
            "badge": m["badge"] or (m["code"] or "")[:4].upper(),
            "due": due, "due_done": due_done,
            "tasks_total": tt, "tasks_done": td,
            "projects_total": pt, "projects_done": pd,
            "comments": int(cmt_by_co.get(m["id"], 0)),
            "score": _score(tt, td),  # метрика — % от всех задач компании
        })

    tm = trow._mapping
    return {
        "tasks_total": int(tm["total"]), "tasks_done": int(tm["done"]),
        "due_total": int(tm["due"]), "due_done": int(tm["due_done"]),
        "projects_total": int(prow._mapping["total"]), "projects_done": int(prow._mapping["done"]),
        "overdue": int(tm["overdue"]) + int(prow._mapping["overdue"]),
        "companies": companies,
    }


async def capture_snapshot(
    db: AsyncSession, *, year: int, label: Optional[str] = None,
    captured_by=None, scope: str = "portfolio",
) -> ProgressSnapshot:
    """Зафиксировать срез прогресса портфеля на текущий момент.

    Переиспользуется HTTP-эндпоинтом и автозахватом (snapshot_scheduler).
    """
    st = await _compute_state(db, year)
    now = datetime.now(UTC)
    snap = ProgressSnapshot(
        captured_at=now, captured_by=captured_by,
        label=label or f"Срез {now.strftime('%d.%m.%Y %H:%M')}",
        year=year, scope=scope,
        tasks_total=st["tasks_total"], tasks_done=st["tasks_done"],
        projects_total=st["projects_total"], projects_done=st["projects_done"],
        overdue=st["overdue"], due_total=st["due_total"], due_done=st["due_done"],
        companies=st["companies"],
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return snap


@router.post("/snapshot", status_code=201)
async def create_snapshot(
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_require_monitoring),
):
    """Зафиксировать срез прогресса портфеля на текущий момент."""
    snap = await capture_snapshot(db, year=body.year, label=body.label, captured_by=user.id)
    return {
        "id": str(snap.id), "captured_at": snap.captured_at.isoformat(), "label": snap.label,
        "year": snap.year, "score": _score(snap.tasks_total, snap.tasks_done) or 0,
        "companies_count": len(snap.companies or []),
    }


def _snap_state(s: ProgressSnapshot) -> dict:
    return {
        "tasks_total": s.tasks_total, "tasks_done": s.tasks_done,
        "due_total": s.due_total, "due_done": s.due_done,
        "projects_total": s.projects_total, "projects_done": s.projects_done,
        "overdue": s.overdue, "companies": s.companies or [],
    }


@router.get("/snapshots")
async def list_snapshots(
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
):
    q = select(ProgressSnapshot).order_by(ProgressSnapshot.captured_at.desc()).limit(50)
    if year is not None:
        q = q.where(ProgressSnapshot.year == year)
    rows = (await db.execute(q)).scalars().all()
    return {
        "items": [
            {
                "id": str(s.id), "captured_at": s.captured_at.isoformat(), "label": s.label,
                "year": s.year, "score": _score(s.tasks_total, s.tasks_done) or 0,
                "overdue": s.overdue,
            }
            for s in rows
        ],
        "total": len(rows),
    }


async def _plan_quarters(db: AsyncSession, year: int) -> list[dict]:
    """Нарастающий план/факт по кварталам (за весь год):
    план = % задач, чей дедлайн ≤ конца квартала; факт = % из них выполнено.
    """
    base = and_(Task.is_archived.is_(False), Task.portfolio_year == year, Task.due_date.is_not(None))
    total = int((await db.execute(select(func.count()).where(base))).scalar() or 0)
    ends = [(1, "I"), (2, "II"), (3, "III"), (4, "IV")]
    out = []
    for q, label in ends:
        qend = _month_end(year, q * 3)
        r = (await db.execute(select(
            func.count().filter(Task.due_date <= qend).label("due"),
            func.count().filter(and_(Task.due_date <= qend, Task.status == "done")).label("done"),
        ).where(base))).first()
        due, done = int(r._mapping["due"]), int(r._mapping["done"])
        out.append({
            "q": q, "label": label,
            "plan_pct": round(due / total * 100) if total else 0,
            "fact_pct": round(done / total * 100) if total else 0,
        })
    return out


@router.get("/digest/{year}")
async def digest(
    year: int,
    period: str = Query("all", pattern="^(all|q[1-4]|m([1-9]|1[0-2]))$"),
    from_id: Optional[str] = Query(None),
    to_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
):
    """Обзор. Всегда возвращает live `current` (в границах period: год/квартал/
    месяц): факт %, «должно быть к сегодня» %, per-company, план по кварталам.
    Плюс `comparison` (было→стало, improved/fell) — если есть базовый срез.
    """
    bounds = _period_bounds(year, period)

    snaps = (await db.execute(
        select(ProgressSnapshot).where(ProgressSnapshot.year == year)
        .order_by(ProgressSnapshot.captured_at.desc()),
    )).scalars().all()
    by_id = {str(s.id): s for s in snaps}

    # ── LIVE current (всегда, в границах period) ──
    if to_id and to_id in by_id:
        to_state, to_label, to_dt = _snap_state(by_id[to_id]), by_id[to_id].label, by_id[to_id].captured_at
    else:
        to_state = await _compute_state(db, year, bounds)
        to_label, to_dt = "Сейчас", datetime.now(UTC)

    total, done = to_state["tasks_total"], to_state["tasks_done"]
    # «Исполнение портфеля» = ПРОСТОЕ среднее % по компаниям (как «Средний прогресс»),
    # а не взвешенное done/total — каждая компания весит одинаково. План — так же.
    # Срезы без per-company (снапшоты) → fallback на взвешенное.
    _cos = to_state.get("companies") or []
    _fp = [round(c["tasks_done"] / c["tasks_total"] * 100) for c in _cos if (c.get("tasks_total") or 0) > 0]
    _pp = [round((c.get("due") or 0) / c["tasks_total"] * 100) for c in _cos if (c.get("tasks_total") or 0) > 0]
    _fact = round(sum(_fp) / len(_fp)) if _fp else (_score(total, done) or 0)
    _plan = round(sum(_pp) / len(_pp)) if _pp else (_score(total, to_state["due_total"]) or 0)
    current = {
        "label": to_label, "at": to_dt.isoformat(), "period": period,
        "score": _fact,               # факт: простое среднее % по компаниям
        "fact_now": _fact,
        "plan_now": _plan,            # «должно быть к сегодня» — тоже среднее по компаниям
        "tasks_done": done, "tasks_total": total,
        "overdue": to_state["overdue"],
        "quarters": await _plan_quarters(db, year),
        "companies": sorted(to_state["companies"], key=lambda c: (c.get("score") if c.get("score") is not None else -1)),
    }

    # ── COMPARISON (было→стало) — год-уровень, если есть срез ──
    comparison = None
    from_s = None
    if from_id and from_id in by_id:
        from_s = by_id[from_id]
    else:
        for s in snaps:
            if not (to_id and str(s.id) == to_id):
                from_s = s
                break
    if from_s is not None:
        from_state, from_dt = _snap_state(from_s), from_s.captured_at
        # сравнение per-company по % от всех задач (пересчёт из сырых полей —
        # устойчиво к смене метрики; старые снимки тоже корректны)
        def coscore(c):
            return _score(c.get("tasks_total", 0) or 0, c.get("tasks_done", 0) or 0)
        fmap = {c["company_id"]: c for c in from_state["companies"]}

        # Обогащаем live-список компаний снимочными значениями: «было → стало»
        # по задачам/проектам/комментам (конкретные цифры на момент среза vs сейчас).
        for c in current["companies"]:
            fc = fmap.get(c["company_id"], {})
            c["tasks_done_snap"] = int(fc.get("tasks_done", 0) or 0)
            c["projects_done_snap"] = int(fc.get("projects_done", 0) or 0)
            c["comments_snap"] = int(fc.get("comments", 0) or 0)
        current["snap_label"] = from_s.label
        current["snap_at"] = from_dt.isoformat()

        improved, fell = [], []
        for c in to_state["companies"]:
            fc = fmap.get(c["company_id"], {})
            fs, ts = coscore(fc), coscore(c)
            if fs is None or ts is None:
                continue
            d = ts - fs
            item = {
                "company_id": c["company_id"], "code": c.get("code"), "name": c["name"],
                "sector": c.get("sector"), "color": c.get("color"), "badge": c.get("badge"),
                "from": fs, "to": ts, "delta": d,
                "tasks_from": int(fc.get("tasks_done", 0) or 0), "tasks_to": int(c.get("tasks_done", 0) or 0),
                "projects_from": int(fc.get("projects_done", 0) or 0), "projects_to": int(c.get("projects_done", 0) or 0),
                "tasks_total": int(c.get("tasks_total", 0) or 0), "projects_total": int(c.get("projects_total", 0) or 0),
                "comments_from": int(fc.get("comments", 0) or 0), "comments_to": int(c.get("comments", 0) or 0),
            }
            if d > 0: improved.append(item)
            elif d < 0: fell.append(item)
        improved.sort(key=lambda x: -x["delta"])
        fell.sort(key=lambda x: x["delta"])

        comments_added = 0
        for cmodel in (TaskComment, ProjectComment):
            comments_added += int((await db.execute(select(func.count()).where(
                cmodel.created_at > from_dt, cmodel.created_at <= to_dt,
            ))).scalar() or 0)

        fp = _score(from_state["tasks_total"], from_state["tasks_done"])
        tp = current["score"]
        comparison = {
            "from": {"label": from_s.label, "at": from_dt.isoformat(), "score": fp or 0},
            "to": {"label": to_label, "at": to_dt.isoformat(), "score": tp},
            "portfolio_delta": (tp - fp) if fp is not None else None,
            "improved": improved, "fell": fell,
            "tasks_closed": done - from_state["tasks_done"],
            "comments_added": comments_added,
        }

    # доступные годы — data-driven (distinct portfolio_year + текущий год),
    # чтобы новый год (напр. 2027) появлялся в селекторе автоматически, как
    # только заведены задачи/проекты за него
    yrs = (await db.execute(
        select(Task.portfolio_year).where(Task.portfolio_year.is_not(None)).distinct(),
    )).scalars().all()
    pyrs = (await db.execute(
        select(Project.portfolio_year).where(Project.portfolio_year.is_not(None)).distinct(),
    )).scalars().all()
    available_years = sorted(
        {int(y) for y in list(yrs) + list(pyrs)} | {datetime.now(UTC).year},
        reverse=True,
    )

    return {
        "year": year, "period": period,
        "available_years": available_years,
        "has_baseline": from_s is not None,
        "current": current,
        "comparison": comparison,
        "snapshots": [{"id": str(s.id), "label": s.label, "at": s.captured_at.isoformat(),
                       "score": _score(s.tasks_total, s.tasks_done) or 0} for s in snaps],
    }


@router.delete("/snapshot/{snap_id}", status_code=204)
async def delete_snapshot(
    snap_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
):
    try:
        sid = UUID(snap_id)
    except Exception as e:
        raise HTTPException(400, "Bad id") from e
    s = await db.get(ProgressSnapshot, sid)
    if not s:
        raise HTTPException(404, "Снимок не найден")
    await db.delete(s)
    await db.commit()


# ════════════════════════════════════════════════════════════
#   AI Executive Brief — агентный нарратив для борда
# ════════════════════════════════════════════════════════════

@router.post("/brief/{year}")
async def exec_brief(
    year: int,
    period: str = Query("all", pattern="^(all|q[1-4]|m([1-9]|1[0-2]))$"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_require_monitoring),
):
    """Сгенерировать executive-бриф по исполнению портфеля (AI engine, grounded в
    реальных цифрах). Уважает is_enabled + owner-активацию ассистента."""
    from app.api.routes.ai import _assistant_active
    from app.services.ai_service import complete_once, is_enabled

    if not is_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI не настроен")
    if not await _assistant_active(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ИИ-ассистент деактивирован владельцем")

    bounds = _period_bounds(year, period)
    st = await _compute_state(db, year, bounds)
    total, done = st["tasks_total"], st["tasks_done"]
    fact = _score(total, done) or 0
    plan = _score(total, st["due_total"]) or 0
    quarters = await _plan_quarters(db, year)
    cos = sorted(
        [c for c in st["companies"] if c.get("score") is not None],
        key=lambda c: c["score"],
    )
    facts = {
        "год": year, "период": period,
        "исполнение_факт_%": fact,
        "должно_быть_к_сегодня_%": plan,
        "отставание_пп": plan - fact,
        "всего_задач": total, "выполнено": done, "просрочено": st["overdue"],
        "компаний": len(st["companies"]),
        "план_по_кварталам_нарастающим": [
            {"кв": q["label"], "план_%": q["plan_pct"], "факт_%": q["fact_pct"]} for q in quarters
        ],
        "отстающие_компании": [
            {"компания": c["name"], "исполнение_%": c["score"],
             "выполнено": c["tasks_done"], "всего": c["tasks_total"]}
            for c in cos[:6]
        ],
        "лидеры": [
            {"компания": c["name"], "исполнение_%": c["score"]} for c in cos[-3:][::-1]
        ],
    }

    system = (
        "Ты — старший портфельный аналитик для Совета директоров холдинга, "
        "управляющего 22 государственными предприятиями Узбекистана (горнодобыча, "
        "нефтегаз, энергетика, транспорт, химия). Пишешь строго по-деловому, на "
        "русском, для высшего руководства. Используй ТОЛЬКО предоставленные цифры — "
        "ничего не выдумывай, не добавляй данных, которых нет. Без воды и общих фраз, "
        "конкретно и по существу. Метрика «исполнение обязательств» = из задач, чей "
        "срок уже наступил, сколько выполнено."
    )
    prompt = (
        "Составь краткий executive-бриф по исполнению портфеля (4–6 абзацев, можно "
        "с подзаголовками):\n"
        "1) Общий статус — где мы по исполнению vs план («должно быть к сегодня»).\n"
        "2) Главные риски — какие компании критично отстают и чем это грозит.\n"
        "3) Траектория по кварталам — успеваем ли к концу года.\n"
        "4) 2–3 конкретные рекомендации Совету (что поручить и кому/по какому "
        "направлению).\n\n"
        f"Данные (JSON):\n{json.dumps(facts, ensure_ascii=False, indent=2)}"
    )
    try:
        text = await complete_once(system=system, prompt=prompt, max_tokens=1700, temperature=0.3)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ошибка генерации: {e}") from e

    return {"brief": text, "facts": facts, "generated_at": datetime.now(UTC).isoformat()}
