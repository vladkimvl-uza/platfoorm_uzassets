"""PMO — загрузка ресурсов (Team / capacity, PMBOK 7).

Считается вживую из назначений задач: на каждого исполнителя — открытые/
просроченные/завершённые задачи и взвешенная загрузка (сумма весов открытых
задач). Без отдельной таблицы — источник те же задачи, что и расписание.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.progress import is_task_overdue
from app.models.company import Company
from app.models.task import Task
from app.schemas.pmo import WorkloadPerson, WorkloadResponse

_CLOSED = {"done", "deferred"}


def _capacity(load: int) -> str:
    if load <= 0:
        return "free"
    if load <= 4:
        return "normal"
    if load <= 9:
        return "high"
    return "overload"


async def compute_workload(
    db: AsyncSession, company_code: str, today: date, year: Optional[int] = None,
) -> Optional[WorkloadResponse]:
    company = (
        await db.execute(select(Company).where(Company.code == company_code))
    ).scalar_one_or_none()
    if company is None:
        return None

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

    people: dict[str, dict] = {}
    unassigned_open = 0
    total_open = 0

    for t in tasks:
        is_open = t.status not in _CLOSED
        if is_open:
            total_open += 1
        key = (
            str(t.assignee_id) if t.assignee_id
            else (t.assignee_name.strip().lower() if t.assignee_name else None)
        )
        if key is None:
            if is_open:
                unassigned_open += 1
            continue
        p = people.get(key)
        if p is None:
            p = {
                "person_id": t.assignee_id,
                "name": (t.assignee_name or "").strip() or "—",
                "assigned": 0, "open": 0, "overdue": 0, "done": 0, "load": 0,
            }
            people[key] = p
        # имя — берём непустое, если первое было пустым
        if (not p["name"] or p["name"] == "—") and t.assignee_name:
            p["name"] = t.assignee_name.strip()
        p["assigned"] += 1
        if t.status == "done":
            p["done"] += 1
        if is_open:
            p["open"] += 1
            p["load"] += int(t.weight or 1)
            if is_task_overdue(t.status, t.due_date, today=today):
                p["overdue"] += 1

    out = [
        WorkloadPerson(
            person_id=p["person_id"], name=p["name"],
            assigned=p["assigned"], open=p["open"], overdue=p["overdue"],
            done=p["done"], load=p["load"], capacity=_capacity(p["load"]),
        )
        for p in people.values()
    ]
    out.sort(key=lambda x: (x.load, x.open), reverse=True)
    max_load = max((p.load for p in out), default=0)

    return WorkloadResponse(
        company_code=company_code,
        as_of=today,
        people=out,
        total_people=len(out),
        total_open=total_open,
        unassigned_open=unassigned_open,
        max_load=max_load,
    )
