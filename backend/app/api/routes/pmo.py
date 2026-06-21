"""PMO API — P1: расписание (Гантт) + зависимости задач.

Тонкий роутер. Чтение расписания гейтится `pmo.view`, правка зависимостей —
`pmo.edit`. Доступ к данным компании — через `ensure_company_access`
(per-company scope, как в остальных модулях).
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.security import has_effective_permission
from app.models.company import Company
from app.models.pmo import RaidItem, StatusReport
from app.models.task import Task, TaskDependency
from app.models.user import User
from app.schemas.pmo import (
    DependencyCreate,
    DependencyRead,
    HealthResponse,
    RaidItemCreate,
    RaidItemRead,
    RaidItemUpdate,
    ScheduleResponse,
    StatusReportCreate,
    StatusReportRead,
)
from app.services.pmo.health import compute_health, generate_status_report
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


# ═══ RAID register (P2) ════════════════════════════════════════════════

async def _raid_or_404(db: AsyncSession, item_id: UUID) -> RaidItem:
    item = (await db.execute(select(RaidItem).where(RaidItem.id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Запись RAID не найдена")
    return item


@router.get("/companies/{code}/raid", response_model=list[RaidItemRead])
async def list_raid(
    code: str,
    kind: Optional[str] = None,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа к RAID (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    q = select(RaidItem).where(RaidItem.company_id == company.id)
    if kind:
        q = q.where(RaidItem.kind == kind)
    if status_filter:
        q = q.where(RaidItem.status == status_filter)
    q = q.order_by(RaidItem.score.desc(), RaidItem.created_at.desc())
    return list((await db.execute(q)).scalars().all())


@router.post("/companies/{code}/raid", response_model=RaidItemRead, status_code=http_status.HTTP_201_CREATED)
async def create_raid(
    code: str,
    payload: RaidItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку RAID (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    data = payload.model_dump()
    item = RaidItem(
        company_id=company.id,
        score=int(payload.probability) * int(payload.impact),
        created_by=user.id,
        closed_at=datetime.now(timezone.utc) if payload.status == "closed" else None,
        **data,
    )
    db.add(item)
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/raid/{item_id}", response_model=RaidItemRead)
async def update_raid(
    item_id: UUID,
    payload: RaidItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку RAID (pmo.edit)")
    item = await _raid_or_404(db, item_id)
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    fields = payload.model_dump(exclude_unset=True)
    for k, v in fields.items():
        setattr(item, k, v)
    item.score = int(item.probability) * int(item.impact)
    if item.status == "closed" and item.closed_at is None:
        item.closed_at = datetime.now(timezone.utc)
    if item.status != "closed":
        item.closed_at = None
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/raid/{item_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_raid(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку RAID (pmo.edit)")
    item = await _raid_or_404(db, item_id)
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    await db.delete(item)
    await db.commit()


# ═══ Здоровье / авто-RAG (P2) ══════════════════════════════════════════

@router.get("/companies/{code}/health", response_model=HealthResponse)
async def get_health(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    try:
        result = await compute_health(db, code, date.today())
    except Exception:
        log.exception("PMO health failed for %s", code)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось рассчитать здоровье портфеля. Попробуйте позже.",
        )
    if result is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Компания «{code}» не найдена")
    return result


# ═══ Статус-отчёты (P2) ════════════════════════════════════════════════

@router.get("/companies/{code}/status-reports", response_model=list[StatusReportRead])
async def list_status_reports(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    rows = (
        await db.execute(
            select(StatusReport)
            .where(StatusReport.company_id == company.id)
            .order_by(StatusReport.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    return list(rows)


@router.post("/companies/{code}/status-reports", response_model=StatusReportRead, status_code=http_status.HTTP_201_CREATED)
async def create_status_report(
    code: str,
    payload: StatusReportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права формировать отчёт (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    try:
        rep = await generate_status_report(db, code, payload.project_id, payload.use_ai, user.id, date.today())
    except Exception:
        log.exception("PMO status-report failed for %s", code)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сформировать статус-отчёт. Попробуйте позже.",
        )
    if rep is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Компания «{code}» не найдена")
    return rep
