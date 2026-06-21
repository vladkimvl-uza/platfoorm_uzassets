"""PMO API — P1: расписание (Гантт) + зависимости задач.

Тонкий роутер. Чтение расписания гейтится `pmo.view`, правка зависимостей —
`pmo.edit`. Доступ к данным компании — через `ensure_company_access`
(per-company scope, как в остальных модулях).
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.security import has_effective_permission
from app.models.company import Company
from app.models.task import Task, TaskDependency
from app.models.user import User
from app.schemas.pmo import DependencyCreate, DependencyRead, ScheduleResponse
from app.services.pmo.schedule import build_schedule

log = logging.getLogger(__name__)
router = APIRouter(prefix="/pmo", tags=["pmo"])


async def _company_or_404(db: AsyncSession, code: str) -> Company:
    company = (
        await db.execute(select(Company).where(Company.code == code))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Компания «{code}» не найдена")
    return company


@router.get("/companies/{code}/schedule", response_model=ScheduleResponse)
async def get_schedule(
    code: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа к расписанию (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    try:
        result = await build_schedule(db, code, year, date.today())
    except Exception:
        log.exception("PMO schedule failed for %s/%s", code, year)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось построить расписание. Попробуйте позже.",
        )
    if result is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Компания «{code}» не найдена")
    return result


# ─── Dependencies ──────────────────────────────────────────────────────

async def _load_task(db: AsyncSession, task_id: UUID) -> Task:
    t = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if t is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Задача не найдена")
    return t


async def _would_create_cycle(db: AsyncSession, predecessor_id: UUID, successor_id: UUID) -> bool:
    """True, если successor уже достижим как предшественник predecessor
    (т.е. новое ребро pred→succ замкнёт цикл). BFS по существующим рёбрам."""
    rows = (await db.execute(select(TaskDependency))).scalars().all()
    succ: dict[UUID, list[UUID]] = defaultdict(list)
    for d in rows:
        succ[d.predecessor_id].append(d.successor_id)
    # Достижим ли predecessor из successor по направлению pred→succ?
    seen: set[UUID] = set()
    q = deque([successor_id])
    while q:
        n = q.popleft()
        if n == predecessor_id:
            return True
        for s in succ.get(n, []):
            if s not in seen:
                seen.add(s)
                q.append(s)
    return False


@router.get("/companies/{code}/dependencies", response_model=list[DependencyRead])
async def list_dependencies(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    task_ids = (
        await db.execute(select(Task.id).where(Task.company_id == company.id))
    ).scalars().all()
    if not task_ids:
        return []
    rows = (
        await db.execute(
            select(TaskDependency).where(TaskDependency.successor_id.in_(task_ids))
        )
    ).scalars().all()
    return list(rows)


@router.post("/dependencies", response_model=DependencyRead, status_code=http_status.HTTP_201_CREATED)
async def create_dependency(
    payload: DependencyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку расписания (pmo.edit)")
    if payload.predecessor_id == payload.successor_id:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Задача не может зависеть от себя")

    pred = await _load_task(db, payload.predecessor_id)
    succ = await _load_task(db, payload.successor_id)
    # Доступ — по компании преемника
    if succ.company_id:
        await ensure_company_access(db, user, succ.company_id)

    # Дубликат?
    existing = (
        await db.execute(
            select(TaskDependency).where(
                TaskDependency.predecessor_id == payload.predecessor_id,
                TaskDependency.successor_id == payload.successor_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if await _would_create_cycle(db, payload.predecessor_id, payload.successor_id):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Зависимость создала бы цикл")

    dep = TaskDependency(
        predecessor_id=payload.predecessor_id,
        successor_id=payload.successor_id,
        dep_type=payload.dep_type,
        lag_days=payload.lag_days,
        created_by=user.id,
    )
    db.add(dep)
    await db.flush()
    await db.commit()
    await db.refresh(dep)
    _ = pred  # подавляем «unused» — задача загружена для валидации существования
    return dep


@router.delete("/dependencies/{dep_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_dependency(
    dep_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку расписания (pmo.edit)")
    dep = (
        await db.execute(select(TaskDependency).where(TaskDependency.id == dep_id))
    ).scalar_one_or_none()
    if dep is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Зависимость не найдена")
    succ = (await db.execute(select(Task).where(Task.id == dep.successor_id))).scalar_one_or_none()
    if succ is not None and succ.company_id:
        await ensure_company_access(db, user, succ.company_id)
    await db.delete(dep)
    await db.commit()
