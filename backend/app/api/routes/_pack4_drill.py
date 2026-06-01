"""Pack 7.36 — directions drill endpoint logic.

Один endpoint: `GET /dashboard/executive/directions/{code}` возвращает
подробную разбивку одного направления по компаниям, проектам и задачам.

Источники:
  • projects table   — фильтр direction_id, group by company_id
  • tasks table      — фильтр direction_id, group by company_id
  • companies table  — name + sector per company_id
  • directions table — code → id + label

Логика:
  1. Найти Direction по code → получить UUID
  2. Загрузить все проекты этого направления (active по году)
  3. Загрузить все задачи этого направления (active по году)
  4. Группировать по company_id → собрать списки проектов и задач для каждой
  5. Подтянуть имя/сектор компании
  6. Сортировать компании по числу проектов desc

Параметр year опциональный — если задан, фильтрует по portfolio_year.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes._pack4_blocks import _DIRS
from app.schemas.executive_dashboard import (
    ExecDirectionDrillCompany,
    ExecDirectionDrillProject,
    ExecDirectionDrillResponse,
    ExecDirectionDrillTask,
)

_DIR_BY_CODE: dict[str, dict[str, str]] = {d["id"]: d for d in _DIRS}


def _is_overdue(due: Optional[date], status: str) -> bool:
    if not due or status == "done":
        return False
    return due < date.today()


def _date_to_str(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


async def build_direction_drill(
    db: AsyncSession,
    direction_code: str,
    year: Optional[int] = None,
    *,
    scope_company_ids: Optional[set] = None,
) -> ExecDirectionDrillResponse:
    """Собрать ответ для drill-модалки одного направления.

    Если задан `scope_company_ids` (set[UUID]) — отфильтровываем проекты
    и задачи, которые не относятся к разрешённым юзеру компаниям.
    `None` (по умолчанию) — без фильтра (admin/owner).
    """
    from app.models.company import Company, Direction, Sector
    from app.models.project import Project
    from app.models.task import Task

    dir_meta = _DIR_BY_CODE.get(direction_code)
    if not dir_meta:
        raise ValueError(f"Unknown direction code: {direction_code}")

    # 1. Resolve direction code → UUID
    q = await db.execute(
        select(Direction.id).where(Direction.code == direction_code)
    )
    direction_uuid = q.scalar_one_or_none()
    if direction_uuid is None:
        # Direction is known in _DIRS but not in DB — return empty response
        return ExecDirectionDrillResponse(
            direction_id=direction_code,
            direction_label=dir_meta["label"],
            direction_color=dir_meta["color"],
            progress_pct=0,
            companies_count=0,
            projects_total=0,
            projects_done=0,
            tasks_total=0,
            tasks_done=0,
            tasks_overdue=0,
            assignees_count=0,
            companies=[],
        )

    # 2. Fetch all projects of this direction (filtered by year if specified)
    proj_q = select(Project).where(Project.direction_id == direction_uuid)
    if year is not None:
        # portfolio_year either matches OR is NULL (legacy projects)
        proj_q = proj_q.where(
            (Project.portfolio_year == year) | (Project.portfolio_year.is_(None))
        )
    proj_res = await db.execute(proj_q)
    all_projects: list[Project] = list(proj_res.scalars().all())

    # 3. Fetch all tasks of this direction
    task_q = select(Task).where(Task.direction_id == direction_uuid)
    if year is not None:
        task_q = task_q.where(
            (Task.portfolio_year == year) | (Task.portfolio_year.is_(None))
        )
    task_res = await db.execute(task_q)
    all_tasks: list[Task] = list(task_res.scalars().all())

    # Scope filter: оставляем только сущности из разрешённых компаний.
    # Сущности без company_id (никем не привязанные) скрываем для scoped users.
    if scope_company_ids is not None:
        all_projects = [p for p in all_projects if p.company_id in scope_company_ids]
        all_tasks = [t for t in all_tasks if t.company_id in scope_company_ids]

    # 4. Collect distinct company_ids referenced
    co_ids: set = set()
    for p in all_projects:
        if p.company_id is not None:
            co_ids.add(p.company_id)
    for t in all_tasks:
        if t.company_id is not None:
            co_ids.add(t.company_id)

    # 5. Hydrate company name + sector_code in one query
    co_name: dict[UUID, str] = {}
    co_sector: dict[UUID, str] = {}
    if co_ids:
        co_q = await db.execute(
            select(Company.id, Company.name_ru, Company.code, Sector.code)
            .join(Sector, Company.sector_id == Sector.id, isouter=True)
            .where(Company.id.in_(co_ids))
        )
        for cid, cname_ru, ccode, scode in co_q.all():
            co_name[cid] = cname_ru or ccode or "—"
            co_sector[cid] = scode or "other"

    # 6. Group projects + tasks by company
    by_co: dict[Any, dict[str, Any]] = {}
    for p in all_projects:
        if p.company_id is None:
            continue
        b = by_co.setdefault(p.company_id, {
            "projects": [], "tasks": [],
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0, "tasks_overdue": 0,
        })
        b["projects_total"] += 1
        if p.status == "done":
            b["projects_done"] += 1
        b["projects"].append(ExecDirectionDrillProject(
            id=p.id,
            title=p.title,
            status=p.status or "new",
            due_date=_date_to_str(p.due_date),
            progress_percent=p.progress_percent or 0,
            is_overdue=_is_overdue(p.due_date, p.status or "new"),
            assignee_name=p.assignee_name,
        ))

    for t in all_tasks:
        if t.company_id is None:
            continue
        b = by_co.setdefault(t.company_id, {
            "projects": [], "tasks": [],
            "projects_total": 0, "projects_done": 0,
            "tasks_total": 0, "tasks_done": 0, "tasks_overdue": 0,
        })
        b["tasks_total"] += 1
        if t.status == "done":
            b["tasks_done"] += 1
        overdue = _is_overdue(t.due_date, t.status or "new")
        if overdue:
            b["tasks_overdue"] += 1
        b["tasks"].append(ExecDirectionDrillTask(
            id=t.id,
            title=t.title,
            status=t.status or "new",
            due_date=_date_to_str(t.due_date),
            progress_percent=t.progress_percent or 0,
            is_overdue=overdue,
            assignee_name=t.assignee_name,
            priority=t.priority or "medium",
        ))

    # 7. Build company list, sorted by projects_total desc → tasks_total desc
    companies_out: list[ExecDirectionDrillCompany] = []
    for cid, b in by_co.items():
        # Сортировка проектов в карточке: done → active → review → new → init
        # и по due_date asc внутри статуса. Сначала те, что в работе/завершены,
        # потом не начатые. Просрочённые — сверху.
        status_order = {"done": 0, "active": 1, "review": 1, "new": 2, "init": 3}
        b["projects"].sort(key=lambda p: (
            0 if p.is_overdue else 1,
            status_order.get(p.status, 99),
            p.due_date or "9999",
        ))
        b["tasks"].sort(key=lambda t: (
            0 if t.is_overdue else 1,
            status_order.get(t.status, 99),
            t.due_date or "9999",
        ))
        companies_out.append(ExecDirectionDrillCompany(
            company_id=cid,
            company_name=co_name.get(cid, "—"),
            sector=co_sector.get(cid, "other"),
            projects_total=b["projects_total"],
            projects_done=b["projects_done"],
            tasks_total=b["tasks_total"],
            tasks_done=b["tasks_done"],
            tasks_overdue=b["tasks_overdue"],
            projects=b["projects"],
            tasks=b["tasks"],
        ))
    companies_out.sort(key=lambda c: (-c.projects_total, -c.tasks_total))

    # 8. Roll-up totals for header
    projects_total = sum(c.projects_total for c in companies_out)
    projects_done = sum(c.projects_done for c in companies_out)
    tasks_total = sum(c.tasks_total for c in companies_out)
    tasks_done = sum(c.tasks_done for c in companies_out)
    tasks_overdue = sum(c.tasks_overdue for c in companies_out)
    progress_pct = round(tasks_done / tasks_total * 100) if tasks_total else 0

    # Distinct assignees across all projects + tasks
    assignees: set = set()
    for p in all_projects:
        if p.assignee_name:
            assignees.add(p.assignee_name)
    for t in all_tasks:
        if t.assignee_name:
            assignees.add(t.assignee_name)

    return ExecDirectionDrillResponse(
        direction_id=direction_code,
        direction_label=dir_meta["label"],
        direction_color=dir_meta["color"],
        progress_pct=progress_pct,
        companies_count=len(companies_out),
        projects_total=projects_total,
        projects_done=projects_done,
        tasks_total=tasks_total,
        tasks_done=tasks_done,
        tasks_overdue=tasks_overdue,
        assignees_count=len(assignees),
        companies=companies_out,
    )
