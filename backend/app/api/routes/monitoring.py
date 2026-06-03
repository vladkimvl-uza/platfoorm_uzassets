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


async def _compute_state(db: AsyncSession, year: int) -> dict:
    """Текущее состояние портфеля: обязательства (due/done) + per-company."""
    today = datetime.now(UTC).date()
    due_cond = and_(Task.due_date.is_not(None), Task.due_date <= today)

    tbase = and_(Task.is_archived.is_(False), Task.portfolio_year == year)
    trow = (await db.execute(select(
        func.count().label("total"),
        func.count().filter(Task.status == "done").label("done"),
        func.count().filter(due_cond).label("due"),
        func.count().filter(and_(due_cond, Task.status == "done")).label("due_done"),
        func.count().filter(and_(Task.due_date < today, Task.status != "done")).label("overdue"),
    ).where(tbase))).first()

    pbase = and_(Project.is_archived.is_(False), Project.portfolio_year == year)
    prow = (await db.execute(select(
        func.count().label("total"),
        func.count().filter(Project.status == "done").label("done"),
        func.count().filter(and_(Project.due_date < today, Project.status != "done")).label("overdue"),
    ).where(pbase))).first()

    # per-company обязательства по задачам
    rows = (await db.execute(select(
        Task.company_id.label("cid"),
        func.count().filter(due_cond).label("due"),
        func.count().filter(and_(due_cond, Task.status == "done")).label("due_done"),
        func.count().label("total"),
        func.count().filter(Task.status == "done").label("done"),
    ).where(tbase, Task.company_id.is_not(None)).group_by(Task.company_id))).all()
    by_co = {r._mapping["cid"]: r._mapping for r in rows}

    co_rows = (await db.execute(select(
        Company.id, Company.code, Company.name_short, Company.name_ru,
        Sector.name_ru.label("sec"), Sector.color_hex.label("color"), Sector.short_badge.label("badge"),
    ).join(Sector, Company.sector_id == Sector.id, isouter=True))).all()

    companies = []
    for c in co_rows:
        m = c._mapping
        r = by_co.get(m["id"])
        if not r:
            continue
        due, due_done = int(r["due"]), int(r["due_done"])
        companies.append({
            "company_id": str(m["id"]), "code": m["code"],
            "name": m["name_short"] or m["name_ru"],
            "sector": m["sec"] or "—", "color": m["color"] or "#888780",
            "badge": m["badge"] or (m["code"] or "")[:4].upper(),
            "due": due, "due_done": due_done, "score": _score(due, due_done),
            "tasks_total": int(r["total"]), "tasks_done": int(r["done"]),
        })

    tm = trow._mapping
    return {
        "tasks_total": int(tm["total"]), "tasks_done": int(tm["done"]),
        "due_total": int(tm["due"]), "due_done": int(tm["due_done"]),
        "projects_total": int(prow._mapping["total"]), "projects_done": int(prow._mapping["done"]),
        "overdue": int(tm["overdue"]) + int(prow._mapping["overdue"]),
        "companies": companies,
    }


@router.post("/snapshot", status_code=201)
async def create_snapshot(
    body: SnapshotCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Зафиксировать срез прогресса портфеля на текущий момент."""
    st = await _compute_state(db, body.year)
    now = datetime.now(UTC)
    label = body.label or f"Срез {now.strftime('%d.%m.%Y %H:%M')}"
    snap = ProgressSnapshot(
        captured_at=now, captured_by=user.id, label=label, year=body.year, scope="portfolio",
        tasks_total=st["tasks_total"], tasks_done=st["tasks_done"],
        projects_total=st["projects_total"], projects_done=st["projects_done"],
        overdue=st["overdue"], due_total=st["due_total"], due_done=st["due_done"],
        companies=st["companies"],
    )
    db.add(snap)
    await db.commit()
    await db.refresh(snap)
    return {
        "id": str(snap.id), "captured_at": snap.captured_at.isoformat(), "label": snap.label,
        "year": snap.year, "score": _score(st["due_total"], st["due_done"]) or 0,
        "companies_count": len(st["companies"]),
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
                "year": s.year, "score": _score(s.due_total, s.due_done) or 0,
                "overdue": s.overdue,
            }
            for s in rows
        ],
        "total": len(rows),
    }


@router.get("/digest/{year}")
async def digest(
    year: int,
    from_id: Optional[str] = Query(None),
    to_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Обзор «Что изменилось»: разница двух точек (срез ↔ срез или срез ↔ сейчас).

    По умолчанию: from = последний снимок, to = «сейчас» (live).
    Если снимков нет — needs_baseline=true (нужно зафиксировать базовый срез).
    """
    snaps = (await db.execute(
        select(ProgressSnapshot).where(ProgressSnapshot.year == year)
        .order_by(ProgressSnapshot.captured_at.desc()),
    )).scalars().all()

    if not snaps:
        return {"year": year, "needs_baseline": True, "snapshots": []}

    by_id = {str(s.id): s for s in snaps}

    # to-сторона
    if to_id and to_id in by_id:
        to_s = by_id[to_id]
        to_state, to_label, to_at = _snap_state(to_s), to_s.label, to_s.captured_at.isoformat()
    else:
        to_state = await _compute_state(db, year)
        to_label, to_at = "Сейчас", datetime.now(UTC).isoformat()

    # from-сторона (по умолчанию — последний снимок; если to=этот снимок, берём следующий)
    from_s = None
    if from_id and from_id in by_id:
        from_s = by_id[from_id]
    else:
        for s in snaps:  # snaps DESC
            if not (to_id and str(s.id) == to_id):
                from_s = s
                break
    if from_s is None:
        from_s = snaps[-1]
    from_state, from_label, from_at = _snap_state(from_s), from_s.label, from_s.captured_at.isoformat()

    def pscore(st):
        return _score(st["due_total"], st["due_done"])
    fp, tp = pscore(from_state), pscore(to_state)

    # per-company дельты
    fmap = {c["company_id"]: c for c in from_state["companies"]}
    improved, fell = [], []
    for c in to_state["companies"]:
        cid = c["company_id"]
        fs = fmap.get(cid, {}).get("score")
        ts = c.get("score")
        if fs is None or ts is None:
            continue
        d = ts - fs
        item = {"company_id": cid, "code": c.get("code"), "name": c["name"],
                "sector": c.get("sector"), "color": c.get("color"), "badge": c.get("badge"),
                "from": fs, "to": ts, "delta": d}
        if d > 0:
            improved.append(item)
        elif d < 0:
            fell.append(item)
    improved.sort(key=lambda x: -x["delta"])
    fell.sort(key=lambda x: x["delta"])

    return {
        "year": year, "needs_baseline": False,
        "from": {"label": from_label, "at": from_at, "score": fp},
        "to": {"label": to_label, "at": to_at, "score": tp},
        "portfolio_delta": (tp - fp) if (tp is not None and fp is not None) else None,
        "improved": improved, "fell": fell,
        "tasks_closed": to_state["tasks_done"] - from_state["tasks_done"],
        "overdue_now": to_state["overdue"],
        "snapshots": [{"id": str(s.id), "label": s.label, "at": s.captured_at.isoformat()} for s in snaps],
    }
