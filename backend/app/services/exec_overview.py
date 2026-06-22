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

from app.models.company import Company, Direction, Sector
from app.models.project import Project
from app.models.task import Task
from app.schemas.exec_overview import (
    ExecOverviewCompany,
    ExecOverviewDirection,
    ExecOverviewProject,
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


def _deadline_state(due: Optional[date], today: date, eom: date, eoq: date) -> str:
    if due is None:
        return "none"
    if due < today:
        return "overdue"
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
            progress_percent=int(t.progress_percent or 0),
            due_date=t.due_date,
            deadline_state=_deadline_state(t.due_date, today, eom, eoq),
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
    fin_map: Optional[dict[str, dict]] = None,
) -> ExecOverviewResponse:
    fin_map = fin_map or {}
    eom, eoq = _eom(today), _eoq(today)

    # справочники
    sectors = (await db.execute(select(Sector).order_by(Sector.sort_order, Sector.name_ru))).scalars().all()
    direction_rows = (await db.execute(
        select(Direction).order_by(Direction.sort_order, Direction.name_ru)
    )).scalars().all()
    directions = {d.id: d.name_ru for d in direction_rows}
    companies = (await db.execute(select(Company))).scalars().all()
    if scope is not None:
        allowed = set(scope)
        companies = [c for c in companies if c.id in allowed]
    comp_by_id = {c.id: c for c in companies}
    comp_ids = set(comp_by_id)

    # текущие проекты
    proj_q = select(Project).where(
        Project.is_archived.is_(False),
        Project.status.notin_(_CLOSED),
    )
    if year is not None:
        proj_q = proj_q.where((Project.portfolio_year == year) | (Project.portfolio_year.is_(None)))
    projects = (await db.execute(proj_q)).scalars().all()
    projects = [p for p in projects if p.company_id in comp_ids]

    # группировка проектов по компании
    by_company: dict[UUID, list[ExecOverviewProject]] = {}
    total = overdue = due_month = 0
    for p in projects:
        st = _deadline_state(p.due_date, today, eom, eoq)
        total += 1
        if st == "overdue":
            overdue += 1
        elif st == "month":
            due_month += 1
        by_company.setdefault(p.company_id, []).append(ExecOverviewProject(
            id=p.id, title=p.title, description=p.description,
            direction=directions.get(p.direction_id) if p.direction_id else None,
            direction_id=p.direction_id,
            status=p.status, progress_percent=int(p.progress_percent or 0),
            due_date=p.due_date, deadline_state=st,
        ))

    # сорт проектов: просрочка/ближайший дедлайн вперёд, без даты — в конец
    _rank = {"overdue": 0, "month": 1, "quarter": 2, "later": 3, "none": 4}
    for lst in by_company.values():
        lst.sort(key=lambda x: (_rank.get(x.deadline_state, 5), x.due_date or date.max))

    # компании по секторам (только с текущими проектами)
    comp_dtos: dict[Optional[UUID], list[ExecOverviewCompany]] = {}
    for cid, plist in by_company.items():
        c = comp_by_id.get(cid)
        if not c:
            continue
        ov = sum(1 for x in plist if x.deadline_state == "overdue")
        fin = fin_map.get(str(c.id)) or {}
        dto = ExecOverviewCompany(
            id=c.id, code=c.code, name=c.name_short or c.name_ru,
            total=len(plist), overdue=ov,
            revenue=fin.get("revenue"), profit=fin.get("profit"), fin_year=fin.get("fin_year"),
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
