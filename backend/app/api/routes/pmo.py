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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.i18n import current_locale, tr
from app.core.security import has_effective_permission
from app.models.company import Company
from app.models.project import Project
from app.models.pmo import (
    PmoChange,
    PmoCharter,
    PmoLesson,
    PmoRaci,
    PmoSprint,
    PmoStakeholder,
    RaidItem,
    StatusReport,
)
from app.models.task import Task, TaskDependency
from app.models.user import User
from app.schemas.pmo import (
    ChangeCreate,
    ChangeRead,
    ChangeUpdate,
    CharterCreate,
    CharterRead,
    CharterUpdate,
    AgileResponse,
    DependencyCreate,
    DependencyRead,
    EvmResponse,
    HealthResponse,
    RaciCreate,
    RaciRead,
    RaciUpdate,
    SprintCreate,
    SprintRead,
    SprintUpdate,
    TaskAgilePatch,
    WorkloadResponse,
    LessonCreate,
    LessonRead,
    LessonUpdate,
    RaidItemCreate,
    RaidItemRead,
    RaidItemUpdate,
    ScheduleResponse,
    StakeholderCreate,
    StakeholderRead,
    StakeholderUpdate,
    StatusReportCreate,
    StatusReportRead,
)
from app.services.pmo.agile import build_agile
from app.services.pmo.evm import compute_evm
from app.services.pmo.health import compute_health, generate_status_report
from app.services.pmo.schedule import build_schedule
from app.services.pmo.workload import compute_workload

log = logging.getLogger(__name__)
router = APIRouter(prefix="/pmo", tags=["pmo"])


async def _company_or_404(db: AsyncSession, code: str) -> Company:
    company = (
        await db.execute(select(Company).where(Company.code == code))
    ).scalar_one_or_none()
    if company is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, tr("Компания «{company}» не найдена", current_locale(), company=code))
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
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, tr("Компания «{company}» не найдена", current_locale(), company=code))
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
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, tr("Компания «{company}» не найдена", current_locale(), company=code))
    return result


# ═══ Освоенный объём / EVM (P3) ════════════════════════════════════════

@router.get("/companies/{code}/evm", response_model=EvmResponse)
async def get_evm(
    code: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    try:
        result = await compute_evm(db, code, date.today(), year)
    except Exception:
        log.exception("PMO EVM failed for %s", code)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось рассчитать освоенный объём. Попробуйте позже.",
        )
    if result is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, tr("Компания «{company}» не найдена", current_locale(), company=code))
    return result


# ═══ Agile / спринты (P3) ══════════════════════════════════════════════

_BOARD_STATUSES = {"new", "init", "active", "review", "done", "deferred"}


@router.get("/companies/{code}/agile", response_model=AgileResponse)
async def get_agile(
    code: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    try:
        result = await build_agile(db, code, year)
    except Exception:
        log.exception("PMO agile failed for %s", code)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить Agile-доску. Попробуйте позже.",
        )
    if result is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, tr("Компания «{company}» не найдена", current_locale(), company=code))
    return result


@router.post("/companies/{code}/sprints", response_model=SprintRead, status_code=http_status.HTTP_201_CREATED)
async def create_sprint(
    code: str,
    payload: SprintCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    s = PmoSprint(company_id=company.id, created_by=user.id, **payload.model_dump())
    db.add(s)
    await db.flush()
    await db.commit()
    await db.refresh(s)
    return s


@router.patch("/sprints/{sid}", response_model=SprintRead)
async def update_sprint(
    sid: UUID,
    payload: SprintUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    s = (await db.execute(select(PmoSprint).where(PmoSprint.id == sid))).scalar_one_or_none()
    if s is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Спринт не найден")
    if s.company_id:
        await ensure_company_access(db, user, s.company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.commit()
    await db.refresh(s)
    return s


@router.delete("/sprints/{sid}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_sprint(
    sid: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    s = (await db.execute(select(PmoSprint).where(PmoSprint.id == sid))).scalar_one_or_none()
    if s is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Спринт не найден")
    if s.company_id:
        await ensure_company_access(db, user, s.company_id)
    # задачи спринта вернутся в бэклог (sprint_id → NULL по FK ON DELETE SET NULL)
    await db.delete(s)
    await db.commit()


@router.patch("/tasks/{task_id}/agile", response_model=AgileResponse)
async def patch_task_agile(
    task_id: UUID,
    payload: TaskAgilePatch,
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Привязать задачу к спринту / снять в бэклог, задать story points, сменить
    статус (drag по доске). Возвращает свежую Agile-доску компании."""
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    t = await _load_task(db, task_id)
    # Авторизуем именно компанию доски (code), которую вернём в ответе, а не только
    # компанию задачи — иначе ответом утекала чужая Agile-доска (IDOR по ?code=).
    company = (await db.execute(
        select(Company).where(Company.code == code)
    )).scalar_one_or_none()
    if company is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Компания не найдена")
    await ensure_company_access(db, user, company.id)
    if t.company_id and t.company_id != company.id:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST,
                            "Задача не принадлежит указанной компании")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in _BOARD_STATUSES:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Недопустимый статус")

    new_status = data.get("status")
    status_changing = "status" in data and str(t.status) != str(new_status)
    _old_status = t.status

    # Спринт / story points — не модерируются (не влияют на прогресс/KPI),
    # применяем сразу. Статус — отдельно, через модерационный гейт.
    for k, v in data.items():
        if k == "status":
            continue
        setattr(t, k, v)

    queued = False
    if status_changing:
        # Перетаскивание карточки по Agile-доске = та же смена статуса задачи,
        # что и через PATCH /tasks/{id}: раньше здесь был прямой setattr+commit в
        # обход модерации и без уведомлений — ограниченный пользователь применял
        # статус (в т.ч. «Готово» → 100% прогресса платформенно) мимо гейта.
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="tasks", action="status_change",
            entity_id=str(task_id), entity_label=f"Задача: {t.title}",
            company_id=t.company_id, sector_id=None, year=t.portfolio_year,
            payload={"status": new_status},
            diff_summary=f"Статус задачи '{t.title}': {_old_status} → {new_status}",
        )
        if queued:
            await db.commit()  # спринт/points применены, статус — на модерации
            return JSONResponse(
                status_code=http_status.HTTP_202_ACCEPTED,
                content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
            )
        t.status = new_status

    await db.commit()

    # Уведомления при фактической смене статуса — как в PATCH /tasks/{id}.
    if status_changing and not queued:
        from app.services.tasks.notifications import notify_task_status_change
        await notify_task_status_change(
            db, task=t, old_status=_old_status, new_status=new_status, actor=user,
        )
        from app.services import watch_service
        await watch_service.notify_watchers(
            db, entity_type="task", entity_id=str(t.id), actor_id=user.id,
            notif_type="watch.status",
            title="Статус отслеживаемой задачи изменён",
            body=f"{user.full_name or user.email}: {_old_status} → {new_status}",
            title_template="Статус отслеживаемой задачи изменён",
            payload={
                "entity_type": "task", "entity_id": str(t.id),
                "entity_title": t.title,
                "action": "status_changed",
                "old_status": _old_status, "new_status": new_status,
            },
        )

    result = await build_agile(db, code, None)
    if result is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Компания не найдена")
    return result


# ═══ Загрузка ресурсов / Workload (P3) ═════════════════════════════════

@router.get("/companies/{code}/workload", response_model=WorkloadResponse)
async def get_workload(
    code: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    try:
        result = await compute_workload(db, code, date.today(), year)
    except Exception:
        log.exception("PMO workload failed for %s", code)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось рассчитать загрузку команды. Попробуйте позже.",
        )
    if result is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, tr("Компания «{company}» не найдена", current_locale(), company=code))
    return result


# ═══ RACI-матрица (P3) ═════════════════════════════════════════════════

@router.get("/companies/{code}/raci", response_model=list[RaciRead])
async def list_raci(
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
            select(PmoRaci).where(PmoRaci.company_id == company.id)
            .order_by(PmoRaci.created_at)
        )
    ).scalars().all()
    return list(rows)


@router.post("/companies/{code}/raci", response_model=RaciRead, status_code=http_status.HTTP_201_CREATED)
async def create_raci(
    code: str,
    payload: RaciCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    item = PmoRaci(company_id=company.id, created_by=user.id, **payload.model_dump())
    db.add(item)
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/raci/{rid}", response_model=RaciRead)
async def update_raci(
    rid: UUID,
    payload: RaciUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoRaci).where(PmoRaci.id == rid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Запись RACI не найдена")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/raci/{rid}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_raci(
    rid: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoRaci).where(PmoRaci.id == rid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Запись RACI не найдена")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    await db.delete(item)
    await db.commit()


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
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права формировать отчёт (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    if payload.use_ai:
        from app.api.routes.ai import require_ai_feature_access
        await require_ai_feature_access(request, user, db)
    try:
        rep = await generate_status_report(db, code, payload.project_id, payload.use_ai, user.id, date.today())
    except Exception:
        log.exception("PMO status-report failed for %s", code)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сформировать статус-отчёт. Попробуйте позже.",
        )
    if rep is None:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND,
            tr("Компания «{company}» не найдена", current_locale(), company=code),
        )
    return rep


# ═══ Стейкхолдеры (PMBOK 7) ════════════════════════════════════════════

async def _stk_or_404(db: AsyncSession, sid: UUID) -> PmoStakeholder:
    s = (await db.execute(select(PmoStakeholder).where(PmoStakeholder.id == sid))).scalar_one_or_none()
    if s is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Стейкхолдер не найден")
    return s


@router.get("/companies/{code}/stakeholders", response_model=list[StakeholderRead])
async def list_stakeholders(
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
            select(PmoStakeholder)
            .where(PmoStakeholder.company_id == company.id)
            .order_by((PmoStakeholder.power * PmoStakeholder.interest).desc(), PmoStakeholder.name)
        )
    ).scalars().all()
    return list(rows)


@router.post("/companies/{code}/stakeholders", response_model=StakeholderRead, status_code=http_status.HTTP_201_CREATED)
async def create_stakeholder(
    code: str,
    payload: StakeholderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    s = PmoStakeholder(company_id=company.id, created_by=user.id, **payload.model_dump())
    db.add(s)
    await db.flush()
    await db.commit()
    await db.refresh(s)
    return s


@router.patch("/stakeholders/{sid}", response_model=StakeholderRead)
async def update_stakeholder(
    sid: UUID,
    payload: StakeholderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    s = await _stk_or_404(db, sid)
    if s.company_id:
        await ensure_company_access(db, user, s.company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.commit()
    await db.refresh(s)
    return s


@router.delete("/stakeholders/{sid}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_stakeholder(
    sid: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    s = await _stk_or_404(db, sid)
    if s.company_id:
        await ensure_company_access(db, user, s.company_id)
    await db.delete(s)
    await db.commit()


# ═══ Журнал: извлечённые уроки (PMBOK 7) ═══════════════════════════════

@router.get("/companies/{code}/lessons", response_model=list[LessonRead])
async def list_lessons(
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
            select(PmoLesson).where(PmoLesson.company_id == company.id)
            .order_by(PmoLesson.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("/companies/{code}/lessons", response_model=LessonRead, status_code=http_status.HTTP_201_CREATED)
async def create_lesson(
    code: str,
    payload: LessonCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    item = PmoLesson(company_id=company.id, created_by=user.id, **payload.model_dump())
    db.add(item)
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/lessons/{lid}", response_model=LessonRead)
async def update_lesson(
    lid: UUID,
    payload: LessonUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoLesson).where(PmoLesson.id == lid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Урок не найден")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/lessons/{lid}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_lesson(
    lid: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoLesson).where(PmoLesson.id == lid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Урок не найден")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    await db.delete(item)
    await db.commit()


# ═══ Журнал: запросы на изменение (PMBOK 7) ════════════════════════════

def _apply_change_decision(item: PmoChange) -> None:
    """Решённый статус → штамп decided_at; обратно в proposed → снять."""
    if item.status in ("approved", "rejected", "implemented"):
        if item.decided_at is None:
            item.decided_at = datetime.now(timezone.utc)
    else:
        item.decided_at = None


@router.get("/companies/{code}/changes", response_model=list[ChangeRead])
async def list_changes(
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
            select(PmoChange).where(PmoChange.company_id == company.id)
            .order_by(PmoChange.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("/companies/{code}/changes", response_model=ChangeRead, status_code=http_status.HTTP_201_CREATED)
async def create_change(
    code: str,
    payload: ChangeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    item = PmoChange(company_id=company.id, created_by=user.id, **payload.model_dump())
    _apply_change_decision(item)
    db.add(item)
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/changes/{cid}", response_model=ChangeRead)
async def update_change(
    cid: UUID,
    payload: ChangeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoChange).where(PmoChange.id == cid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Изменение не найдено")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    _apply_change_decision(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/changes/{cid}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_change(
    cid: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoChange).where(PmoChange.id == cid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Изменение не найдено")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    await db.delete(item)
    await db.commit()


# ═══ Устав проекта (PMBOK 7 — Charter) ═════════════════════════════════

def _apply_charter_approval(item: PmoCharter, actor: User) -> None:
    """status=approved → штамп approver+дата; обратно в draft → снять."""
    if item.status == "approved":
        if item.approved_at is None:
            item.approved_at = datetime.now(timezone.utc)
            item.approved_by = actor.full_name or actor.email
    else:
        item.approved_at = None
        item.approved_by = None


@router.get("/companies/{code}/charters", response_model=list[CharterRead])
async def list_charters(
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
            select(PmoCharter).where(PmoCharter.company_id == company.id)
            .order_by(PmoCharter.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.get("/companies/{code}/charter-prefill")
async def charter_prefill(
    code: str,
    project_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Черновик устава из УЖЕ имеющихся данных проекта.

    Аудит PMO показал корень пустых уставов: всё приходится набивать руками,
    хотя половина сведений уже есть в проекте и его задачах. Возвращаем
    ПРЕДЛОЖЕНИЕ — фронт подставляет его в пустые поля формы и помечает
    источник; введённое пользователем не трогаем.

    Правила: РП — ответственный проекта; бюджет/даты — поля проекта; вехи —
    задачи с признаком is_milestone; ключевые результаты — завершённые задачи;
    границы (scope in) — перечень задач проекта.
    """
    if not await has_effective_permission(db, user, "pmo.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет доступа (pmo.view)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)

    out: dict = {"fields": {}, "sources": {}}
    if project_id is None:
        return out

    project = (await db.execute(
        select(Project).where(Project.id == project_id, Project.company_id == company.id)
    )).scalar_one_or_none()
    if project is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Проект не найден")

    tasks = (await db.execute(
        select(Task).where(Task.project_id == project.id, Task.is_archived.is_(False))
        .order_by(Task.due_date.asc().nullslast())
    )).scalars().all()

    def _put(field: str, value, source: str) -> None:
        if value in (None, "", []):
            return
        out["fields"][field] = value
        out["sources"][field] = source

    _put("manager_name", project.assignee_name, "ответственный проекта")
    _put("budget_amount", float(project.budget_amount) if project.budget_amount is not None else None,
         "бюджет проекта")
    _put("start_date", project.start_date.isoformat() if project.start_date else None,
         "старт проекта")
    _put("target_end_date", project.due_date.isoformat() if project.due_date else None,
         "срок проекта")
    _put("purpose", project.description, "описание проекта")

    nl = chr(10)

    milestones = [t for t in tasks if getattr(t, "is_milestone", False)]
    if milestones:
        _put("milestones", nl.join(
            f"• {t.title}" + (f" — {t.due_date.isoformat()}" if t.due_date else "")
            for t in milestones[:20]
        ), f"вехи проекта ({len(milestones)})")

    done = [t for t in tasks if t.status == "done"]
    if done:
        _put("deliverables", nl.join(f"• {t.title}" for t in done[:20]),
             f"завершённые задачи ({len(done)})")

    if tasks:
        _put("scope_in", nl.join(f"• {t.title}" for t in tasks[:30]),
             f"задачи проекта ({len(tasks)})")

    return out


@router.post("/companies/{code}/charters", response_model=CharterRead, status_code=http_status.HTTP_201_CREATED)
async def create_charter(
    code: str,
    payload: CharterCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    company = await _company_or_404(db, code)
    await ensure_company_access(db, user, company.id)
    # один устав на проект — если уже есть, возвращаем существующий
    if payload.project_id is not None:
        existing = (
            await db.execute(
                select(PmoCharter).where(
                    PmoCharter.company_id == company.id,
                    PmoCharter.project_id == payload.project_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
    item = PmoCharter(company_id=company.id, created_by=user.id, **payload.model_dump())
    db.add(item)
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/charters/{cid}", response_model=CharterRead)
async def update_charter(
    cid: UUID,
    payload: CharterUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoCharter).where(PmoCharter.id == cid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Устав не найден")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    _apply_charter_approval(item, user)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/charters/{cid}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_charter(
    cid: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "pmo.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Нет права на правку (pmo.edit)")
    item = (await db.execute(select(PmoCharter).where(PmoCharter.id == cid))).scalar_one_or_none()
    if item is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Устав не найден")
    if item.company_id:
        await ensure_company_access(db, user, item.company_id)
    await db.delete(item)
    await db.commit()
