"""Boards and Tasks API.

Endpoints:
  GET    /boards                  list boards with task counts
  GET    /boards/{id}             single board detail
  GET    /boards/{id}/kanban      board with tasks grouped by status (kanban)
  GET    /tasks                   list tasks (filterable)
  GET    /tasks/{id}              single task detail
  POST   /tasks                   create task
  PATCH  /tasks/{id}              update task (auto-logs to task_history)
  DELETE /tasks/{id}              archive task

All endpoints require auth. RBAC permissions: tasks.view / tasks.edit /
tasks.delete; boards.view.
"""
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import _has_permission, get_current_user
from app.database import get_db
from app.models.board import Board
from app.models.company import Company
from app.models.task import Task, TaskHistory, TaskComment, TaskHistory
from app.models.project import Project
from app.models.user import User
from app.schemas.task import (
    BoardBrief, BoardKanban, BoardListResponse,
    KanbanColumn, TaskBrief, TaskCreate, TaskDetail,
    TaskListResponse, TaskUpdate,
)


# Status presentation тАФ verbatim from monolith (line 50585-50588 of index.html).
# Order matches STATUSES; labels are SLABELS; colors are SDOTS.
# This drives the Kanban column ordering and chip styling.
STATUS_META = [
    ("new",       "╨Э╨╡ ╨╜╨░╤З╨░╤В╨╛",         "#CBD5E1"),
    ("init",      "╨Ш╨╜╨╕╤Ж╨╕╨╕╤А╨╛╨▓╨░╨╜╨╕╨╡",     "#7F77DD"),
    ("active",    "╨Т ╨┐╤А╨╛╤Ж╨╡╤Б╤Б╨╡",        "#378ADD"),
    ("review",    "╨Э╨░ ╤Б╨╛╨│╨╗╨░╤Б╨╛╨▓╨░╨╜╨╕╨╕",   "#EF9F27"),
    ("done",      "╨Ч╨░╨▓╨╡╤А╤И╨╡╨╜╨╛",         "#1D9E75"),
    ("quarterly", "╨Х╨╢╨╡╨║╨▓╨░╤А╤В╨░╨╗╤М╨╜╨╛",     "#A855F7"),
    ("monthly",   "╨Х╨╢╨╡╨╝╨╡╤Б╤П╤З╨╜╨╛",        "#6366F1"),
    ("ongoing",   "╨Я╨╛╤Б╤В╨╛╤П╨╜╨╜╨╛",         "#06B6D4"),
]




# Phase 16: Direction palette + enrichment helper
_DIR_PALETTE = {
    "strategy":    ("╨б╤В╤А╨░╤В╨╡╨│╨╕╤З╨╡╤Б╨║╨╛╨╡ ╤Г╨┐╤А╨░╨▓╨╗╨╡╨╜╨╕╨╡",  "#1e2787"),
    "finance":     ("╨д╨╕╨╜╨░╨╜╤Б╤Л / ╤А╨╕╤Б╨║╨╕ / ╨░╤Г╨┤╨╕╤В",    "#D97706"),
    "procurement": ("╨б╨╕╤Б╤В╨╡╨╝╨░ ╨╖╨░╨║╤Г╨┐╨╛╨║",            "#3B6D11"),
    "orgdev":      ("╨Ю╤А╨│╨░╨╜╨╕╨╖╨░╤Ж╨╕╨╛╨╜╨╜╨╛╨╡ ╤А╨░╨╖╨▓╨╕╤В╨╕╨╡",   "#534AB7"),
    "digital":     ("╨ж╨╕╤Д╤А╨╛╨▓╨╕╨╖╨░╤Ж╨╕╤П",               "#1D9E75"),
    "operations":  ("╨Ю╨┐╨╡╤А╨░╤Ж╨╕╨╛╨╜╨╜╨░╤П ╤Н╤Д╤Д╨╡╨║╤В╨╕╨▓╨╜╨╛╤Б╤В╤М", "#EF4444"),
    "governance":  ("╨Ъ╨╛╤А╨┐╨╛╤А╨░╤В╨╕╨▓╨╜╨╛╨╡ ╤Г╨┐╤А╨░╨▓╨╗╨╡╨╜╨╕╨╡",   "#72243E"),
    "esg":         ("ESG",                        "#1D9E75"),
    "pr":          ("╨б╨▓╤П╨╖╨╕ ╤Б ╨╛╨▒╤Й╨╡╤Б╤В╨▓╨╡╨╜╨╜╨╛╤Б╤В╤М╤О",    "#D4537E"),
    "pmo":         ("PMO",                        "#2563EB"),
    "analytics":   ("╨б╨▓╨╛╨┤╨╜╤Л╨╣ ╨╛╤В╨┤╨╡╨╗",              "#7C3AED"),
}


def _enrich_with_direction_meta(items):
    """For each item with non-null direction string, populate direction_meta dict."""
    for item in items:
        if getattr(item, "direction_meta", None) is not None:
            continue  # already set
        code = getattr(item, "direction", None)
        if not code:
            continue
        code = str(code).lower().strip()
        if code in _DIR_PALETTE:
            label, color = _DIR_PALETTE[code]
            item.direction_meta = {
                "code": code, "label": label, "color": color
            }


router = APIRouter(tags=["tasks"])


# =====================================================================
# Helper: TaskBrief from Task ORM
# =====================================================================

def _task_to_brief(t: Task, board_name: Optional[str] = None,
                   company_code: Optional[str] = None) -> TaskBrief:
    is_overdue = bool(t.due_date and t.status != "done" and t.due_date < date.today())
    extra = t.extra or {}
    return TaskBrief(
        id=t.id, num=t.num, title=t.title,
        status=t.status, priority=t.priority,
        board_id=t.board_id, board_name=board_name,
        company_id=t.company_id, company_code=company_code,
        assignee_email=t.assignee_email, assignee_name=t.assignee_name, assignee_id=t.assignee_id,
        due_date=t.due_date, portfolio_year=t.portfolio_year,
        is_project=False, progress_percent=t.progress_percent,
        is_overdue=is_overdue, tags=t.tags,
        # Monolith-specific (from extra JSONB) тАФ frontend's computeProgress() needs these
        quarters=extra.get("quarters") if isinstance(extra.get("quarters"), dict) else None,
        consultant=extra.get("consultant"),
        direction=extra.get("direction"),
        created_at=t.created_at, updated_at=t.updated_at,
    )


# =====================================================================
# BOARDS
# =====================================================================

@router.get("/boards", response_model=BoardListResponse)
async def list_boards(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sector: Optional[str] = Query(None, description="Filter by sector code"),
    company_id: Optional[UUID] = Query(None),
    archived: bool = Query(False),
    search: Optional[str] = Query(None),
):
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    # Per-company scope
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and len(scope_ids) == 0:
        return BoardListResponse(items=[], total=0)

    q = (select(Board, Company.code, Company.name_short)
         .outerjoin(Company, Board.company_id == Company.id)
         .where(Board.is_archived == archived))
    if scope_ids is not None:
        # Hide boards belonging to companies the user can't see.
        # Boards with no company_id are platform-wide тАФ still hidden from scoped users.
        q = q.where(Board.company_id.in_(scope_ids))
    if sector:
        q = q.where(Board.sector_code == sector.lower())
    if company_id:
        q = q.where(Board.company_id == company_id)
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(func.lower(Board.name).like(s))
    q = q.order_by(Board.sort_order.asc(), Board.name.asc())

    rows = (await db.execute(q)).all()
    board_ids = [r.Board.id for r in rows]

    # Aggregate task counts per board grouped by status
    counts_by_board: dict[UUID, dict[str, int]] = {bid: {} for bid in board_ids}
    if board_ids:
        cnt_q = (select(Task.board_id, Task.status, func.count())
                 .where(Task.board_id.in_(board_ids), Task.is_archived.is_(False))
                 .group_by(Task.board_id, Task.status))
        for bid, st, cnt in (await db.execute(cnt_q)).all():
            counts_by_board[bid][st] = cnt

    items = []
    for r in rows:
        b = r.Board
        cnts = counts_by_board.get(b.id, {})
        items.append(BoardBrief(
            id=b.id, name=b.name, description=b.description,
            color_hex=b.color_hex, sector_code=b.sector_code,
            company_id=b.company_id, company_code=r.code, company_name=r.name_short,
            is_archived=b.is_archived, sort_order=b.sort_order,
            tasks_total=sum(cnts.values()),
            tasks_by_status=cnts,
        ))

    return BoardListResponse(items=items, total=len(items))


@router.get("/boards/{board_id}", response_model=BoardBrief)
async def get_board(
    board_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    q = (select(Board, Company.code, Company.name_short)
         .outerjoin(Company, Board.company_id == Company.id)
         .where(Board.id == board_id))
    row = (await db.execute(q)).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Board not found")

    # Per-company scope check тАФ return 403 to distinguish "exists but no access"
    # from "does not exist". Already-allowed users see this transparently.
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if row.Board.company_id is None or row.Board.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this board")

    b = row.Board
    cnt_q = (select(Task.status, func.count())
             .where(Task.board_id == board_id, Task.is_archived.is_(False))
             .group_by(Task.status))
    cnts = dict((await db.execute(cnt_q)).all())

    return BoardBrief(
        id=b.id, name=b.name, description=b.description,
        color_hex=b.color_hex, sector_code=b.sector_code,
        company_id=b.company_id, company_code=row.code, company_name=row.name_short,
        is_archived=b.is_archived, sort_order=b.sort_order,
        tasks_total=sum(cnts.values()),
        tasks_by_status=cnts,
    )


@router.get("/boards/{board_id}/kanban", response_model=BoardKanban)
async def get_board_kanban(
    board_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    portfolio_year: Optional[int] = Query(None),
):
    """Board with tasks grouped into kanban columns by status."""
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    q = (select(Board, Company.code, Company.name_short)
         .outerjoin(Company, Board.company_id == Company.id)
         .where(Board.id == board_id))
    row = (await db.execute(q)).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Board not found")
    b = row.Board

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if b.company_id is None or b.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this board")

    # Fetch all tasks for this board
    task_q = (select(Task)
              .where(Task.board_id == board_id, Task.is_archived.is_(False)))
    if portfolio_year:
        task_q = task_q.where(Task.portfolio_year == portfolio_year)
    task_q = task_q.order_by(Task.priority.asc(), Task.due_date.asc().nulls_last(), Task.num.asc())
    tasks = (await db.execute(task_q)).scalars().all()

    # Group by status
    by_status: dict[str, list] = {s: [] for s, _, _ in STATUS_META}
    for t in tasks:
        if t.status in by_status:
            by_status[t.status].append(_task_to_brief(t, b.name, row.code))

    columns = [
        KanbanColumn(status=s, label=label, color=color,
                     tasks=by_status[s], count=len(by_status[s]))
        for s, label, color in STATUS_META
    ]

    board_brief = BoardBrief(
        id=b.id, name=b.name, description=b.description,
        color_hex=b.color_hex, sector_code=b.sector_code,
        company_id=b.company_id, company_code=row.code, company_name=row.name_short,
        is_archived=b.is_archived, sort_order=b.sort_order,
        tasks_total=len(tasks),
        tasks_by_status={s: len(by_status[s]) for s in by_status},
    )
    return BoardKanban(board=board_brief, columns=columns)


# =====================================================================
# TASKS
# =====================================================================

@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    board_id: Optional[UUID] = Query(None),
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    status: Optional[str] = Query(None, pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$"),
    direction: Optional[str] = Query(None, description='Filter by direction code'),
    priority: Optional[str] = Query(None, pattern="^(high|medium|low)$"),
    assignee_email: Optional[str] = Query(None),
    portfolio_year: Optional[int] = Query(None),
    only_overdue: bool = Query(False),
    search: Optional[str] = Query(None),
    sort_by: str = Query("updated_at", regex="^(updated_at|created_at|due_date|priority|num)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    # Per-company scope (organization users see only their allowed companies)
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and len(scope_ids) == 0:
        # User has no company access тАФ return empty
        return TaskListResponse(items=[], total=0)

    q = (select(Task, Board.name.label("board_name"), Company.code.label("company_code"))
         .outerjoin(Board, Task.board_id == Board.id)
         .outerjoin(Company, Task.company_id == Company.id)
         .where(Task.is_archived.is_(False)))

    if scope_ids is not None:
        # Strict scope: show ONLY tasks linked to allowed companies. Tasks
        # without a company_id (platform-level) are hidden from scoped users.
        q = q.where(Task.company_id.in_(scope_ids))

    if board_id:        q = q.where(Task.board_id == board_id)
    if company_id:      q = q.where(Task.company_id == company_id)
    if company_code:    q = q.where(func.lower(Company.code) == company_code.lower())
    if status == "deferred":
        q = q.where(Task.linked_year.is_not(None))
    elif status:        q = q.where(Task.status == status)
    if direction:
        from app.models.company import Direction as _DirM
        _dir_id_q = await db.execute(select(_DirM.id).where(_DirM.code == direction))
        _dir_id_row = _dir_id_q.scalar_one_or_none()
        if _dir_id_row is not None:
            q = q.where(Task.direction_id == _dir_id_row)
    if priority:        q = q.where(Task.priority == priority)
    if assignee_email:  q = q.where(func.lower(Task.assignee_email) == assignee_email.lower())
    if portfolio_year:  q = q.where(Task.portfolio_year == portfolio_year)
    if only_overdue:
        q = q.where(Task.due_date < date.today(), Task.status != "done")
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(Task.title).like(s),
            func.lower(Task.num).like(s),
            func.lower(Task.assignee_name).like(s),
            func.lower(Task.assignee_email).like(s),
        ))

    # Total before limit
    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    # Sort
    sort_col = {
        "updated_at": Task.updated_at,
        "created_at": Task.created_at,
        "due_date":   Task.due_date,
        "priority":   Task.priority,
        "num":        Task.num,
    }.get(sort_by, Task.updated_at)
    q = q.order_by(asc(sort_col).nulls_last() if sort_dir == "asc" else desc(sort_col).nulls_last())
    q = q.limit(limit).offset(offset)

    rows = (await db.execute(q)).all()
    items = [_task_to_brief(r.Task, r.board_name, r.company_code) for r in rows]

    # Aggregate counts by status / priority for the SAME filter (less the status/priority filters themselves)
    counts_q_status = select(Task.status, func.count()).where(Task.is_archived.is_(False))
    counts_q_prio   = select(Task.priority, func.count()).where(Task.is_archived.is_(False))
    if scope_ids is not None:
        counts_q_status = counts_q_status.where(Task.company_id.in_(scope_ids))
        counts_q_prio   = counts_q_prio.where(Task.company_id.in_(scope_ids))
    if board_id:
        counts_q_status = counts_q_status.where(Task.board_id == board_id)
        counts_q_prio   = counts_q_prio.where(Task.board_id == board_id)
    if company_id:
        counts_q_status = counts_q_status.where(Task.company_id == company_id)
        counts_q_prio   = counts_q_prio.where(Task.company_id == company_id)
    counts_q_status = counts_q_status.group_by(Task.status)
    counts_q_prio   = counts_q_prio.group_by(Task.priority)

    by_status   = dict((await db.execute(counts_q_status)).all())
    by_priority = dict((await db.execute(counts_q_prio)).all())

    # Deferred (linkedYear set) count тАФ Phase 13
    def_q = (select(func.count()).select_from(Task)
             .where(Task.is_archived.is_(False),
                    Task.linked_year.is_not(None)))
    if scope_ids is not None:
        def_q = def_q.where(Task.company_id.in_(scope_ids))
    if board_id:    def_q = def_q.where(Task.board_id == board_id)
    if company_id:  def_q = def_q.where(Task.company_id == company_id)
    if portfolio_year: def_q = def_q.where(Task.portfolio_year == portfolio_year)
    by_status['deferred'] = (await db.execute(def_q)).scalar() or 0

    # Available years for year selector (independent of current year filter,
    # but still respects company access scope)
    yr_q = (select(Task.portfolio_year, func.count())
            .where(Task.portfolio_year.is_not(None), Task.is_archived.is_(False)))
    if scope_ids is not None:
        yr_q = yr_q.where(Task.company_id.in_(scope_ids))
    yr_q = yr_q.group_by(Task.portfolio_year).order_by(Task.portfolio_year.desc())
    available_years = [y for y, _ in (await db.execute(yr_q)).all()]

    return TaskListResponse(
        items=items, total=total,
        by_status=by_status, by_priority=by_priority,
        available_years=available_years,
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    q = (select(Task, Board.name.label("board_name"), Company.code.label("company_code"))
         .outerjoin(Board, Task.board_id == Board.id)
         .outerjoin(Company, Task.company_id == Company.id)
         .where(Task.id == task_id))
    row = (await db.execute(q)).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if row.Task.company_id is None or row.Task.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")

    t = row.Task
    base = _task_to_brief(t, row.board_name, row.company_code)
    _enrich_with_direction_meta([base])
    extra = t.extra or {}
    return TaskDetail(
        **base.model_dump(),
        description=t.description,
        scope=extra.get("scope"),
        consultants=extra.get("consultants", []) or [],
        extra=extra,
        legacy_id=t.legacy_id,
        creator_id=t.creator_id,
        start_date=t.start_date,
        completed_at=t.completed_at,
    )


@router.post("/tasks", response_model=TaskDetail, status_code=http_status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")

    # Per-company scope: scoped users can only create tasks for their allowed companies
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if payload.company_id is None or payload.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot create task for a company outside your allowed list",
            )

    # Validate board exists if provided
    if payload.board_id:
        board_check = await db.execute(select(Board.id).where(Board.id == payload.board_id))
        if not board_check.scalar_one_or_none():
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Board {payload.board_id} not found")

    # Build extra JSONB from monolith-specific fields. We bundle them into
    # one column rather than adding many sparse columns тАФ they're rarely
    # all-set together and frontend reads them as a unit anyway.
    extra: dict = {}
    if payload.consultant is not None:
        extra["consultant"] = payload.consultant
    if payload.consultant_comment is not None:
        extra["consultant_comment"] = payload.consultant_comment
    if payload.economic_effect is not None:
        extra["economic_effect"] = payload.economic_effect
    if payload.quarters is not None:
        extra["quarters"] = payload.quarters
    if payload.direction is not None:
        extra["direction"] = payload.direction
    if payload.scope is not None:
        extra["scope"] = payload.scope

    task = Task(
        title=payload.title,
        description=payload.description,
        num=payload.num,
        status=payload.status,
        priority=payload.priority,
        board_id=payload.board_id,
        company_id=payload.company_id,
        project_id=payload.project_id,
        direction_id=payload.direction_id,
        assignee_email=payload.assignee_email,
        assignee_name=payload.assignee_name,
        start_date=payload.start_date,
        due_date=payload.due_date,
        portfolio_year=payload.portfolio_year,
        tags=payload.tags,
        extra=extra or None,
        creator_id=user.id,
    )
    db.add(task)
    await db.flush()

    # Audit history
    db.add(TaskHistory(
        task_id=task.id, actor_id=user.id, action="created",
        new_value=f"{task.title}",
    ))
    await db.commit()
    await db.refresh(task)

    # Pack 13.2.4: notify assignee on create
    if payload.assignee_email:
        await _notify_task_assignment(
            db,
            task=task,
            old_email=None,
            new_email=payload.assignee_email,
            actor=user,
        )

    return await _hydrate_detail(db, task)


@router.patch("/tasks/{task_id}", response_model=TaskDetail)
async def update_task(
    task_id: UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")

    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if task.company_id is None or task.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")
        # Also block reassigning the task to a company outside the user's scope
        new_company_id = payload.model_dump(exclude_unset=True).get("company_id")
        if new_company_id is not None and new_company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot reassign task to a company outside your allowed list",
            )

    changes = payload.model_dump(exclude_unset=True)

    # Pack 13.2.4: snapshot assignee_email before mutation for later notify()
    _old_assignee_email = task.assignee_email

    # Separate monolith-specific fields (live in extra JSONB) from real columns.
    # Without this split, `setattr(task, "quarters", ...)` would raise because
    # there's no `quarters` column on the Task model.
    EXTRA_FIELDS = {"consultant", "consultant_comment", "economic_effect", "quarters", "direction", "scope"}
    extra_updates = {k: changes.pop(k) for k in list(changes.keys()) if k in EXTRA_FIELDS}

    # Capture old values for audit log on tracked fields
    audit_fields = {"status", "title", "priority", "assignee_email",
                    "assignee_name", "due_date", "num", "board_id"}
    history_entries = []
    for field, new_value in changes.items():
        if field in audit_fields:
            old_value = getattr(task, field)
            if str(old_value or "") != str(new_value or ""):
                history_entries.append(TaskHistory(
                    task_id=task.id, actor_id=user.id,
                    action="status_changed" if field == "status" else "field_updated",
                    field_name=field,
                    old_value=str(old_value or ""), new_value=str(new_value or ""),
                ))

    # Apply updates
    for field, value in changes.items():
        setattr(task, field, value)

    # Merge monolith-specific updates into the extra JSONB. Any key explicitly
    # set in the payload overwrites the existing one; null/None CLEARS the key
    # (treats explicit null as "unset this field"). This matches the monolith's
    # behaviour where saving the editor with cleared consultant removes the consultant.
    if extra_updates:
        merged = dict(task.extra or {})
        for k, v in extra_updates.items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
        task.extra = merged or None

    # Auto-fill completed_at when status moves to done
    if changes.get("status") == "done" and not task.completed_at:
        task.completed_at = datetime.now(timezone.utc)

    # Auto-clear completed_at when status moves away from done
    if "status" in changes and changes["status"] != "done":
        task.completed_at = None

    for h in history_entries:
        db.add(h)
    # Auto-align year if task linked to a project (silent, logged in task_history)
    await _align_task_year(db, task, getattr(user, 'id', None))
    await db.commit()
    await db.refresh(task)

    # Pack 13.2.4: notify new assignee if assignee_email changed
    if "assignee_email" in changes:
        await _notify_task_assignment(
            db,
            task=task,
            old_email=_old_assignee_email,
            new_email=changes.get("assignee_email"),
            actor=user,
        )

    return await _hydrate_detail(db, task)


@router.delete("/tasks/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def archive_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "tasks.delete"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.delete")

    res = await db.execute(select(Task).where(Task.id == task_id))
    task = res.scalar_one_or_none()
    if not task:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Task not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if task.company_id is None or task.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this task")

    task.is_archived = True
    db.add(TaskHistory(task_id=task.id, actor_id=user.id, action="archived"))
    await db.commit()


# =====================================================================
# Helpers
# =====================================================================


async def _align_task_year(
    db: AsyncSession,
    task: Task,
    actor_id=None,
) -> bool:
    """Silently align task.portfolio_year to project.portfolio_year if mismatched.
    Logs the change to task_history. Returns True if year was changed.
    """
    if not task.project_id:
        return False
    project = await db.get(Project, task.project_id)
    if not project or not project.portfolio_year:
        return False
    if task.portfolio_year == project.portfolio_year:
        return False
    old_year = task.portfolio_year
    task.portfolio_year = project.portfolio_year
    db.add(TaskHistory(
        task_id=task.id,
        actor_id=actor_id,
        action="auto_aligned",
        field_name="portfolio_year",
        old_value=str(old_year) if old_year is not None else None,
        new_value=str(project.portfolio_year),
    ))
    return True

async def _notify_task_assignment(
    db: AsyncSession,
    *,
    task: Task,
    old_email: Optional[str],
    new_email: Optional[str],
    actor: User,
) -> None:
    """Pack 13.2.4: emit `assignment` notification when task gets a new assignee.

    No-op if:
      - new_email is empty / unchanged
      - no User row matches new_email (legacy assignee, no in-app account)

    Also denormalizes task.assignee_id from the resolved User when not set yet.
    notify() handles WS push + DB row + (Pack 13.2.3) async Telegram forward.
    Self-assignment is intentionally NOT filtered - users sometimes self-assign
    to verify pipelines.
    """
    if not new_email:
        return
    if new_email == old_email:
        return
    res = await db.execute(select(User).where(User.email == new_email))
    target = res.scalar_one_or_none()
    if not target:
        return  # legacy assignee, no user account
    if task.assignee_id != target.id:
        task.assignee_id = target.id
        await db.commit()
        await db.refresh(task)
    from app.services.notifications_service import notify
    body = (task.description or "")[:200] or None
    await notify(
        db,
        recipient_id=target.id,
        type="assignment",
        title=f"\u0417\u0430\u0434\u0430\u0447\u0430 \u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0430: {task.title}",
        body=body,
        source_module="tasks",
        source_entity_id=str(task.id),
        source_user_id=actor.id,
        payload={
            "task_id": str(task.id),
            "task_num": task.num,
            "board_id": str(task.board_id) if task.board_id else None,
            "company_id": str(task.company_id) if task.company_id else None,
        },
        link_url=f"/tasks/{task.id}",
    )


async def _hydrate_detail(db: AsyncSession, task: Task) -> TaskDetail:
    board_name = None
    company_code = None
    if task.board_id:
        b = (await db.execute(select(Board.name).where(Board.id == task.board_id))).scalar_one_or_none()
        board_name = b
    if task.company_id:
        c = (await db.execute(select(Company.code).where(Company.id == task.company_id))).scalar_one_or_none()
        company_code = c

    base = _task_to_brief(task, board_name, company_code)
    extra = task.extra or {}

    # Load task comments with author info
    cmt_rows = await db.execute(
        select(TaskComment).where(TaskComment.task_id == task.id).order_by(TaskComment.created_at.desc()).limit(100)
    )
    cmt_objs = cmt_rows.scalars().all()
    comments_list = []
    if cmt_objs:
        author_ids = list({c.author_id for c in cmt_objs if c.author_id})
        author_map = {}
        if author_ids:
            users_rows = await db.execute(select(User).where(User.id.in_(author_ids)))
            for u in users_rows.scalars().all():
                name = getattr(u, "full_name", None) or getattr(u, "name", None) or getattr(u, "email", None)
                author_map[u.id] = (name, getattr(u, "email", None))
        for c in cmt_objs:
            name, email = author_map.get(c.author_id, (None, None))
            comments_list.append({
                "id": str(c.id),
                "author_id": str(c.author_id) if c.author_id else None,
                "author_name": name,
                "author_email": email,
                "body": c.body,
                "is_edited": c.is_edited,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            })
    return TaskDetail(
        **base.model_dump(),
        description=task.description,
        scope=extra.get("scope"),
        consultants=extra.get("consultants", []) or [],
        extra=extra,
        legacy_id=task.legacy_id,
        creator_id=task.creator_id,
        start_date=task.start_date,
        completed_at=task.completed_at,
        # Monolith-specific (also in extra; expose at top-level for cleaner API)
        consultant_comment=extra.get("consultant_comment"),
        economic_effect=extra.get("economic_effect") if isinstance(extra.get("economic_effect"), dict) else None,
        comments=comments_list,
    )
