"""Boards and Tasks API — thin HTTP layer (refactored 2026-05-25).

10-layer template:
  routes → dependencies → services → uow → repositories.

Endpoints (без изменений URL):
  GET    /boards                        list boards с task counts
  GET    /boards/{id}                   single board
  GET    /boards/{id}/kanban            kanban-grouped tasks
  GET    /tasks                         list tasks (filterable)
  GET    /tasks/{id}                    task detail
  POST   /tasks                         create task
  PATCH  /tasks/{id}                    update task (auto-logs history)
  POST   /tasks/{id}/result             toggle результат-flag
  DELETE /tasks/{id}                    archive task

Auth: tasks.view / tasks.edit / tasks.delete; boards.view.
Moderation gate + side-effect notifications выполняются в route после service
(чтобы хранить HTTP-concern отдельно от бизнес-логики).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.tasks import TasksEditorServiceDep, TasksQueryServiceDep
from app.models.user import User
from app.schemas.task import (
    BoardBrief,
    BoardKanban,
    BoardListResponse,
    TaskCreate,
    TaskDetail,
    TaskListResponse,
    TaskUpdate,
)

router = APIRouter(tags=["tasks"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"Permission required: {code}")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else None


# ─── Boards ───────────────────────────────────────────────────────

@router.get("/boards", response_model=BoardListResponse)
async def list_boards(
    service: TasksQueryServiceDep,
    sector: Optional[str] = Query(None),
    company_id: Optional[UUID] = Query(None),
    archived: bool = Query(False),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.view")
    return await service.list_boards(
        scope_company_ids=await _scope(db, user),
        sector=sector, company_id=company_id,
        archived=archived, search=search,
    )


@router.get("/boards/{board_id}", response_model=BoardBrief)
async def get_board(
    board_id: UUID,
    service: TasksQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.view")
    return await service.get_board(board_id, scope_company_ids=await _scope(db, user))


@router.get("/boards/{board_id}/kanban", response_model=BoardKanban)
async def get_board_kanban(
    board_id: UUID,
    service: TasksQueryServiceDep,
    portfolio_year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.view")
    return await service.get_board_kanban(
        board_id,
        scope_company_ids=await _scope(db, user),
        portfolio_year=portfolio_year,
    )


# ─── Tasks queries ────────────────────────────────────────────────

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    service: TasksQueryServiceDep,
    board_id: Optional[UUID] = Query(None),
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$"),
    direction: Optional[str] = Query(None),
    priority: Optional[str] = Query(None, pattern="^(high|medium|low)$"),
    assignee_email: Optional[str] = Query(None),
    portfolio_year: Optional[int] = Query(None),
    only_overdue: bool = Query(False),
    search: Optional[str] = Query(None),
    sort_by: str = Query("updated_at", regex="^(updated_at|created_at|due_date|priority|num)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tasks with rich filtering: board, company, status, priority,
    assignee, portfolio year, overdue-only, search.

    Requires `tasks.view`. Results are scoped to the caller's company access set."""
    await _require(db, user, "tasks.view")
    return await service.list_tasks(
        scope_company_ids=await _scope(db, user),
        board_id=board_id, company_id=company_id, company_code=company_code,
        status=status, direction=direction, priority=priority,
        assignee_email=assignee_email, portfolio_year=portfolio_year,
        only_overdue=only_overdue, search=search,
        sort_by=sort_by, sort_dir=sort_dir, limit=limit, offset=offset,
        current_user_id=user.id,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: UUID,
    service: TasksQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch single task by id with all relations (board, project, assignee, watchers).

    Returns 404 if the task is outside the caller's company scope."""
    await _require(db, user, "tasks.view")
    return await service.get_task(task_id, scope_company_ids=await _scope(db, user))


# ─── Tasks mutations ──────────────────────────────────────────────

@router.post("/tasks", response_model=TaskDetail, status_code=http_status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    service: TasksEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new task. May queue for moderation if the caller is restricted.

    Requires `tasks.edit`. Returns 202 with a `submission_id` if held for
    moderation; otherwise 201 with the created task. Notifies the assignee on
    create."""
    await _require(db, user, "tasks.edit")

    # Per-company scope check before moderation gate
    scope_ids = await _scope(db, user)
    if scope_ids is not None:
        if payload.company_id is None or payload.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot create task for a company outside your allowed list",
            )

    # Moderation gate
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="tasks", action="create",
        entity_id=None, entity_label=f"Задача: {payload.title}",
        company_id=payload.company_id, sector_id=None,
        year=payload.portfolio_year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Новая задача · {payload.priority or '—'} · {payload.title}",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    task, new_assignee_email = await service.create_task(payload, creator_id=user.id)

    # Side-effect: notify assignee on create
    if new_assignee_email:
        from app.services.tasks.notifications import notify_task_assignment
        await notify_task_assignment(
            db, task=task, old_email=None,
            new_email=new_assignee_email, actor=user,
        )

    # Watch: автор и исполнитель авто-подписываются на задачу
    from app.services import watch_service
    await watch_service.auto_follow(db, user.id, "task", str(task.id))
    await watch_service.auto_follow_email(db, new_assignee_email, "task", str(task.id))
    await db.commit()

    return await service.hydrate_detail(task)


@router.patch("/tasks/{task_id}", response_model=TaskDetail)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    service: TasksEditorServiceDep,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.edit")
    scope_ids = await _scope(db, user)

    # Moderation gate (нужен title — поэтому ранний lookup в DB)
    from sqlalchemy import select

    from app.models.task import Task
    pre = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one_or_none()
    if not pre:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")

    # Захватываем срок ДО апдейта — для уведомления «изменил срок» (pre и task —
    # один identity-объект сессии, после update pre.due_date уже новый).
    _old_due = pre.due_date.isoformat() if pre.due_date else None

    changed = payload.model_dump(mode="json", exclude_unset=True)
    # Реальный diff: только поля, чьё значение действительно отличается от текущего
    # (редактор шлёт весь объект, поэтому exclude_unset недостаточно). pre ещё хранит
    # старые значения — апдейт ниже. Для детали owner.activity «Изменено: …».
    _real_changed: list[str] = []
    for _k, _v in changed.items():
        _ov = getattr(pre, _k, None)
        _ov = _ov.isoformat() if hasattr(_ov, "isoformat") else _ov
        if str(_ov) != str(_v):
            _real_changed.append(_k)
    request.state.activity_fields = _real_changed
    # Деталь уведомления при смене статуса: «Статус: Новая → Завершено».
    if "status" in changed and str(getattr(pre, "status", None)) != str(changed.get("status")):
        from app.services.owner_activity import status_label as _stl
        request.state.activity_summary = (
            f"Статус: {_stl(getattr(pre, 'status', None))} → {_stl(changed.get('status'))}"
        )
        request.state.activity_entity = getattr(pre, "title", None)
    # Если в апдейте меняется статус — действие "status_change" (правила могут
    # таргетить именно смену статуса); иначе обычный "update" (→ canon "edit").
    mod_action = "status_change" if "status" in changed else "update"
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="tasks", action=mod_action,
        entity_id=str(task_id), entity_label=f"Задача: {pre.title}",
        company_id=pre.company_id, sector_id=None, year=pre.portfolio_year,
        payload=changed,
        diff_summary=f"Обновление задачи '{pre.title}'",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )

    task, info = await service.update_task(
        task_id, payload, actor_id=user.id, scope_company_ids=scope_ids,
    )

    # Side-effects
    if info["description_changed"] and info["mention_text"]:
        from app.services.mention_service import notify_mentioned_users
        await notify_mentioned_users(
            db, text=info["mention_text"],
            actor_id=user.id,
            actor_name=user.full_name or user.email,
            entity_type="task", entity_id=str(task.id),
            entity_title=task.title or "(без названия)",
            company_id=getattr(task, "company_id", None),
            link_url=f"/tasks/{task.id}",
        )

    if info["assignee_changed"]:
        from app.services.tasks.notifications import notify_task_assignment
        await notify_task_assignment(
            db, task=task,
            old_email=info["old_assignee_email"],
            new_email=info["new_assignee_email"],
            actor=user,
        )
        # Watch: новый исполнитель авто-подписывается
        from app.services import watch_service
        await watch_service.auto_follow_email(db, info["new_assignee_email"], "task", str(task.id))
        await db.commit()

    if info.get("status_changed"):
        from app.services.tasks.notifications import notify_task_status_change
        await notify_task_status_change(
            db, task=task,
            old_status=info.get("old_status"),
            new_status=info.get("new_status"),
            actor=user,
        )
        # Watch: уведомить отслеживающих эту задачу
        from app.services import watch_service
        await watch_service.notify_watchers(
            db, entity_type="task", entity_id=str(task.id), actor_id=user.id,
            notif_type="watch.status",
            title="Статус отслеживаемой задачи изменён",
            body=f"{user.full_name or user.email}: {info.get('old_status')} → {info.get('new_status')}",
            title_template="Статус отслеживаемой задачи изменён",
            payload={
                "entity_type": "task", "entity_id": str(task.id),
                "entity_title": task.title,
                "action": "status_changed",
                "old_status": info.get("old_status"),
                "new_status": info.get("new_status"),
            },
        )

    # Изменение срока — отдельное уведомление отслеживающим (что именно поменялось).
    _new_due = task.due_date.isoformat() if task.due_date else None
    if "due_date" in changed and _new_due != _old_due:
        from app.services import watch_service as _ws
        await _ws.notify_watchers(
            db, entity_type="task", entity_id=str(task.id), actor_id=user.id,
            notif_type="watch.deadline",
            title="Срок отслеживаемой задачи изменён",
            body=f"{user.full_name or user.email}: {_old_due or '—'} → {_new_due or '—'}",
            title_template="Срок отслеживаемой задачи изменён",
            payload={
                "entity_type": "task", "entity_id": str(task.id),
                "entity_title": task.title,
                "action": "deadline_changed",
                "old_due": _old_due, "new_due": _new_due,
            },
        )

    return await service.hydrate_detail(task)


@router.post("/tasks/{task_id}/result", status_code=http_status.HTTP_200_OK)
async def toggle_task_result(
    task_id: UUID,
    service: TasksEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.edit")
    res = await service.toggle_result(
        task_id, actor_id=user.id, scope_company_ids=await _scope(db, user),
    )
    from app.services import watch_service
    await watch_service.notify_watchers(
        db, entity_type="task", entity_id=str(task_id), actor_id=user.id,
        notif_type="watch.result",
        title="Результат отслеживаемой задачи обновлён",
        body=f"{user.full_name or user.email} отметил(а) результат",
        title_template="Результат отслеживаемой задачи обновлён",
        body_template="{actor} отметил(а) результат",
        template_vars={"actor": user.full_name or user.email},
        payload={"entity_type": "task", "entity_id": str(task_id), "action": "result"},
    )
    return res


@router.delete("/tasks/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def archive_task(
    task_id: UUID,
    service: TasksEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.delete")
    await service.archive_task(
        task_id, actor_id=user.id, scope_company_ids=await _scope(db, user),
    )
