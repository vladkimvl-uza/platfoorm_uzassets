"""PMO — Agile/Scrum представление (PMBOK 7).

Спринт группирует существующие задачи (tasks.sprint_id). Сервис собирает
спринты + задачи компании в форме для бэклога и доски спринта. Никакой новой
сущности рабочих элементов — переиспользуем Task.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.pmo import PmoSprint
from app.models.project import Project
from app.models.task import Task
from app.schemas.pmo import AgileResponse, AgileTask, SprintRead

_CLOSED = {"done", "deferred"}


async def build_agile(
    db: AsyncSession, company_code: str, year: Optional[int] = None,
) -> Optional[AgileResponse]:
    company = (
        await db.execute(select(Company).where(Company.code == company_code))
    ).scalar_one_or_none()
    if company is None:
        return None

    sprints = (
        await db.execute(
            select(PmoSprint).where(PmoSprint.company_id == company.id)
            .order_by(PmoSprint.created_at)
        )
    ).scalars().all()

    proj_titles = dict(
        (
            await db.execute(
                select(Project.id, Project.title).where(Project.company_id == company.id)
            )
        ).all()
    )

    tasks = (
        await db.execute(
            select(Task).where(
                Task.company_id == company.id,
                Task.is_archived.is_(False),
            )
        )
    ).scalars().all()
    if year is not None:
        tasks = [t for t in tasks if t.portfolio_year in (None, year)]

    agile_tasks = [
        AgileTask(
            id=t.id, title=t.title, status=t.status,
            project_id=t.project_id,
            project_title=proj_titles.get(t.project_id) if t.project_id else None,
            assignee_id=t.assignee_id, assignee_name=t.assignee_name,
            story_points=t.story_points, sprint_id=t.sprint_id,
            due_date=t.due_date, weight=int(t.weight or 1),
        )
        for t in tasks
    ]
    backlog_count = sum(
        1 for t in tasks if t.sprint_id is None and t.status not in _CLOSED
    )

    return AgileResponse(
        company_code=company_code,
        sprints=[SprintRead.model_validate(s) for s in sprints],
        tasks=agile_tasks,
        backlog_count=backlog_count,
    )
