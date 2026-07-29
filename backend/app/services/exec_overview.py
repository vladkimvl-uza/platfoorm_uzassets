"""Executive Overview — сборка иерархии сектор→компания→текущие проекты.

Скоуп: None = весь портфель (министр/owner), список = только разрешённые
компании. «Текущие» = открытые (не завершён/не перенесён), не архивные,
портфельного года.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.progress import is_task_overdue, task_pct, weighted_pct
from app.models.company import Company, Direction, Sector
from app.models.project import Project
from app.models.task import Task
from app.schemas.exec_overview import (
    ExecOverviewCompany,
    ExecOverviewDirection,
    ExecOverviewProject,
    ExecOverviewRating,
    ExecOverviewResponse,
    ExecOverviewSector,
    ExecOverviewTask,
)

_CLOSED = {"done", "deferred"}


def _eom(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _eoq(d: date) -> date:
    qm = ((d.month - 1) // 3 + 1) * 3
    return date(d.year, qm, calendar.monthrange(d.year, qm)[1])


def _deadline_state(due: Optional[date], status: Optional[str], today: date, eom: date, eoq: date) -> str:
    if due is None:
        return "none"
    if is_task_overdue(status, due, today=today):
        return "overdue"
    if due < today:
        return "none"
    if due <= eom:
        return "month"
    if due <= eoq:
        return "quarter"
    return "later"


async def build_project_tasks(
    db: AsyncSession, project_id: UUID, today: date,
) -> list[ExecOverviewTask]:
    """Задачи проекта для разворота по клику (открытые вперёд, по дедлайну)."""
    eom, eoq = _eom(today), _eoq(today)
    rows = (await db.execute(
        select(Task).where(Task.project_id == project_id, Task.is_archived.is_(False))
    )).scalars().all()
    out = [
        ExecOverviewTask(
            id=t.id, title=t.title, status=t.status,
            assignee_name=t.assignee_name,
            progress_percent=task_pct(t.status, t.extra) or 0,
            due_date=t.due_date,
            deadline_state=_deadline_state(t.due_date, t.status, today, eom, eoq),
        )
        for t in rows
    ]
    _rank = {"overdue": 0, "month": 1, "quarter": 2, "later": 3, "none": 4}
    _closed = {"done", "deferred"}
    out.sort(key=lambda x: (x.status in _closed, _rank.get(x.deadline_state, 5), x.due_date or date.max))
    return out


async def build_exec_overview(
    db: AsyncSession,
    scope: Optional[Sequence[UUID]],
    year: Optional[int],
    today: date,
    can_bp: bool = False,
    can_ratings: bool = False,
) -> ExecOverviewResponse:
    from app.models.agency_rating import AgencyRating
    from app.models.status_update import StatusUpdate
    from app.services.bp_kpi_helpers import bp_compute
    eom, eoq = _eom(today), _eoq(today)

    # справочники
    sectors = (await db.execute(select(Sector).order_by(Sector.sort_order, Sector.name_ru))).scalars().all()
    direction_rows = (await db.execute(
        select(Direction).order_by(Direction.sort_order, Direction.name_ru)
    )).scalars().all()
    directions = {d.id: d.name_ru for d in direction_rows}
    co_q = select(Company).where(Company.is_active.is_(True))
    if scope is None:
        # include_in_rollups: демо/непрофильные компании не должны искажать
        # ПОРТФЕЛЬНЫЕ цифры обзора. При явной области выборка уже сужена
        # вызывающим — иначе пользователь, чья область состоит из такой
        # компании, не увидит собственных проектов.
        co_q = co_q.where(Company.include_in_rollups.is_(True))
    companies = (await db.execute(co_q)).scalars().all()
    if scope is not None:
        allowed = set(scope)
        companies = [c for c in companies if c.id in allowed]
    comp_by_id = {c.id: c for c in companies}
    comp_ids = set(comp_by_id)

    # проекты года: показываем ВСЕ (включая завершённые/перенесённые); закрытые
    # помечаем deadline_state="none" ниже — не считаются просроченными, идут в конец.
    proj_q = select(Project).where(Project.is_archived.is_(False))
    if year is not None:
        proj_q = proj_q.where((Project.portfolio_year == year) | (Project.portfolio_year.is_(None)))
    projects = (await db.execute(proj_q)).scalars().all()
    projects = [p for p in projects if p.company_id in comp_ids]

    # задачи проектов — для взвешенного прогресса по новой логике (статусы задач)
    proj_ids = {p.id for p in projects}
    tasks_by_proj: dict[UUID, list[Task]] = {}
    if proj_ids:
        task_rows = (await db.execute(
            select(Task).where(Task.project_id.in_(proj_ids), Task.is_archived.is_(False))
        )).scalars().all()
        for t in task_rows:
            tasks_by_proj.setdefault(t.project_id, []).append(t)

    def _proj_progress(p: Project) -> int:
        kids = tasks_by_proj.get(p.id)
        if kids:
            return weighted_pct((t.status, t.extra) for t in kids)
        return task_pct(p.status, p.extra) or 0

    # «ход проекта»: последний нарративный апдейт по каждому проекту (status_update)
    last_upd: dict[str, "StatusUpdate"] = {}
    if proj_ids:
        su_rows = (await db.execute(
            select(StatusUpdate)
            .where(
                StatusUpdate.entity_type == "project",
                StatusUpdate.entity_id.in_([str(pid) for pid in proj_ids]),
            )
            .order_by(StatusUpdate.created_at.desc())
        )).scalars().all()
        for su in su_rows:
            if su.entity_id not in last_upd:
                last_upd[su.entity_id] = su

    # группировка проектов по компании
    by_company: dict[UUID, list[ExecOverviewProject]] = {}
    total = overdue = due_month = 0
    for p in projects:
        # завершённые/перенесённые — без дедлайн-срочности (не «просрочено», в конец)
        st = "none" if p.status in _CLOSED else _deadline_state(p.due_date, p.status, today, eom, eoq)
        total += 1
        if st == "overdue":
            overdue += 1
        elif st == "month":
            due_month += 1
        su = last_upd.get(str(p.id))
        by_company.setdefault(p.company_id, []).append(ExecOverviewProject(
            id=p.id, title=p.title, description=p.description,
            direction=directions.get(p.direction_id) if p.direction_id else None,
            direction_id=p.direction_id,
            status=p.status, progress_percent=_proj_progress(p),
            due_date=p.due_date, deadline_state=st,
            last_update=su.body if su else None,
            last_update_at=su.created_at.date() if su and su.created_at else None,
            last_update_health=su.health if su else None,
            last_update_author=su.author_name if su else None,
        ))

    # сорт проектов: просрочка/ближайший дедлайн вперёд, без даты — в конец
    _rank = {"overdue": 0, "month": 1, "quarter": 2, "later": 3, "none": 4}
    for lst in by_company.values():
        lst.sort(key=lambda x: (_rank.get(x.deadline_state, 5), x.due_date or date.max))

    # Ключевые результаты бизнес-плана за Q1 (план/факт) по компаниям с текущими
    # проектами — заменяют годовые финпоказатели в обзоре. Гейт bp.view — в роутере.
    yr = year or today.year
    bp_q1: dict[UUID, dict] = {}
    if can_bp:
        def _f(v: object) -> Optional[float]:
            return float(v) if v is not None else None  # type: ignore[arg-type]
        for cid in by_company:
            try:
                comp = await bp_compute(db, cid, yr, "q1")
            except Exception:  # noqa: BLE001
                continue
            rev = comp.get("revenue") or {}
            prof = comp.get("profit") or {}
            if any(x is not None for x in (rev.get("plan"), rev.get("fact"),
                                           prof.get("plan"), prof.get("fact"))):
                bp_q1[cid] = {
                    "rev_plan": _f(rev.get("plan")), "rev_fact": _f(rev.get("fact")),
                    "profit_plan": _f(prof.get("plan")), "profit_fact": _f(prof.get("fact")),
                }

    # Кредитные (rating+outlook) и ESG (score) рейтинги агентств по компаниям.
    # Гейт ratings.view — в роутере. Одна строка на (компания, агентство).
    ratings_by_co: dict[UUID, dict[str, list[ExecOverviewRating]]] = {}
    if can_ratings and comp_ids:
        ar_rows = (await db.execute(
            select(AgencyRating)
            .where(AgencyRating.company_id.in_(comp_ids))
            .order_by(AgencyRating.is_esg, AgencyRating.agency)
        )).scalars().all()
        for r in ar_rows:
            d = ratings_by_co.setdefault(r.company_id, {"credit": [], "esg": []})
            if r.is_esg:
                val = r.score or r.rating  # часть ESG-агентств кладёт балл в rating
                if val:
                    d["esg"].append(ExecOverviewRating(agency=r.agency, score=val))
            elif r.rating:
                d["credit"].append(ExecOverviewRating(
                    agency=r.agency, rating=r.rating, outlook=r.outlook,
                ))

    # компании по секторам (только с текущими проектами)
    comp_dtos: dict[Optional[UUID], list[ExecOverviewCompany]] = {}
    for cid, plist in by_company.items():
        c = comp_by_id.get(cid)
        if not c:
            continue
        ov = sum(1 for x in plist if x.deadline_state == "overdue")
        bp = bp_q1.get(cid) or {}
        rt = ratings_by_co.get(cid) or {}
        dto = ExecOverviewCompany(
            id=c.id, code=c.code, name=c.name_short or c.name_ru,
            total=len(plist), overdue=ov,
            q1_revenue_plan=bp.get("rev_plan"), q1_revenue_fact=bp.get("rev_fact"),
            q1_profit_plan=bp.get("profit_plan"), q1_profit_fact=bp.get("profit_fact"),
            credit_ratings=rt.get("credit", []), esg_ratings=rt.get("esg", []),
            projects=plist,
        )
        comp_dtos.setdefault(c.sector_id, []).append(dto)

    for lst in comp_dtos.values():
        lst.sort(key=lambda x: (-x.overdue, -x.total, x.name))

    # секторы
    out_sectors: list[ExecOverviewSector] = []
    used_company_count = 0
    seen_sector_ids = set()
    for s in sectors:
        clist = comp_dtos.get(s.id, [])
        if not clist:
            continue
        seen_sector_ids.add(s.id)
        used_company_count += len(clist)
        out_sectors.append(ExecOverviewSector(
            id=s.id, code=s.code, name=s.name_ru, color=s.color_hex,
            short_badge=s.short_badge,
            total=sum(c.total for c in clist),
            overdue=sum(c.overdue for c in clist),
            company_count=len(clist),
            companies=clist,
        ))
    # компании без сектора
    orphan = comp_dtos.get(None, [])
    if orphan:
        used_company_count += len(orphan)
        out_sectors.append(ExecOverviewSector(
            id=None, code=None, name="Без сектора", color=None, short_badge=None,
            total=sum(c.total for c in orphan), overdue=sum(c.overdue for c in orphan),
            company_count=len(orphan), companies=orphan,
        ))

    # каталог направлений (только те, что встречаются в текущих проектах) —
    # лейны дорожной карты, в порядке sort_order
    used_dir_ids = {p.direction_id for p in projects if p.direction_id}
    dir_catalog = [
        ExecOverviewDirection(id=d.id, code=d.code, name=d.name_ru)
        for d in direction_rows if d.id in used_dir_ids
    ]

    return ExecOverviewResponse(
        year=year, as_of=today,
        total=total, overdue=overdue, due_this_month=due_month,
        sector_count=len(out_sectors), company_count=used_company_count,
        sectors=out_sectors,
        directions=dir_catalog,
    )
