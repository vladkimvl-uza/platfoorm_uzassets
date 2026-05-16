"""Projects API — long-running initiatives separated from tasks.

Endpoints:
  GET    /projects                 list with filters
  GET    /projects/{id}            single project detail (with child task counts)
  GET    /projects/{id}/tasks      child tasks of this project
  POST   /projects                 create
  PATCH  /projects/{id}            update
  DELETE /projects/{id}            archive
"""
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import _has_permission, get_current_user, has_effective_permission
from app.database import get_db
from app.models.board import Board
from app.models.company import Company
from app.models.project import Project, ProjectComment
from app.models.task import Task
from app.models.user import User
from app.schemas.project import (
    ProjectBrief, ProjectCreate, ProjectDetail,
    ProjectListResponse, ProjectUpdate,
)
from app.schemas.task import TaskBrief




# Phase 16: Direction palette + enrichment helper
_DIR_PALETTE = {
    "strategy":    ("Стратегическое управление",  "#1e2787"),
    "finance":     ("Финансы / риски / аудит",    "#D97706"),
    "procurement": ("Система закупок",            "#3B6D11"),
    "orgdev":      ("Организационное развитие",   "#534AB7"),
    "digital":     ("Цифровизация",               "#1D9E75"),
    "operations":  ("Операционная эффективность", "#EF4444"),
    "governance":  ("Корпоративное управление",   "#72243E"),
    "esg":         ("ESG",                        "#1D9E75"),
    "pr":          ("Связи с общественностью",    "#D4537E"),
    "pmo":         ("PMO",                        "#2563EB"),
    "analytics":   ("Сводный отдел",              "#7C3AED"),
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


router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_brief(p: Project, board_name: Optional[str], company_code: Optional[str],
                      company_name: Optional[str], tasks_total: int = 0, tasks_done: int = 0) -> ProjectBrief:
    is_overdue = bool(p.due_date and p.status != "done" and p.due_date < date.today())
    extra = p.extra or {}
    return ProjectBrief(
        id=p.id, num=p.num, title=p.title,
        status=p.status, priority=p.priority,
        board_id=p.board_id, board_name=board_name,
        company_id=p.company_id, company_code=company_code, company_name=company_name,
        assignee_email=p.assignee_email, assignee_name=p.assignee_name, assignee_id=p.assignee_id,
        due_date=p.due_date, portfolio_year=p.portfolio_year,
        # Phase 14: live progress from done/total tasks
        progress_percent=(round(tasks_done / tasks_total * 100)
                          if tasks_total > 0 else 0),
        is_overdue=is_overdue, tags=p.tags,
        tasks_total=tasks_total, tasks_done=tasks_done,
        # Monolith-specific
        quarters=extra.get("quarters") if isinstance(extra.get("quarters"), dict) else None,
        consultant=extra.get("consultant"),
        direction=extra.get("direction"),
        created_at=p.created_at, updated_at=p.updated_at,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    portfolio_year: Optional[int] = Query(None, description="Year filter (e.g. 2025/2026)"),
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    board_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None, pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$"),
    direction: Optional[str] = Query(None, description='Filter by direction code'),
    priority: Optional[str] = Query(None, pattern="^(high|medium|low)$"),
    assignee_email: Optional[str] = Query(None),
    only_overdue: bool = Query(False),
    has_economic_effect: bool = Query(False, description="Pack 7.33: Filter to projects with extra.economicEffect data (plannedValue or realizedValue > 0)"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("updated_at", regex="^(updated_at|created_at|due_date|priority|num|title)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    # Per-company scope
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None and len(scope_ids) == 0:
        return ProjectListResponse(items=[], total=0)

    q = (select(Project,
                Board.name.label("board_name"),
                Company.code.label("company_code"),
                Company.name_short.label("company_name"))
         .outerjoin(Board, Project.board_id == Board.id)
         .outerjoin(Company, Project.company_id == Company.id)
         .where(Project.is_archived.is_(False)))

    if scope_ids is not None:
        # Strict: only projects linked to user's allowed companies
        q = q.where(Project.company_id.in_(scope_ids))

    if portfolio_year:  q = q.where(Project.portfolio_year == portfolio_year)
    if company_id:      q = q.where(Project.company_id == company_id)
    if company_code:    q = q.where(func.lower(Company.code) == company_code.lower())
    if board_id:        q = q.where(Project.board_id == board_id)
    if status == "deferred":
        q = q.where(Project.linked_year.is_not(None))
    elif status:
        q = q.where(Project.status == status)
    if direction:
        from app.models.company import Direction as _DirM
        _dir_id_q = await db.execute(select(_DirM.id).where(_DirM.code == direction))
        _dir_id_row = _dir_id_q.scalar_one_or_none()
        if _dir_id_row is not None:
            q = q.where(Project.direction_id == _dir_id_row)
    if priority:        q = q.where(Project.priority == priority)
    if assignee_email:  q = q.where(func.lower(Project.assignee_email) == assignee_email.lower())
    if only_overdue:
        q = q.where(Project.due_date < date.today(), Project.status != "done")
    if has_economic_effect:
        # Pack 7.33: фильтр на наличие extra.economicEffect.
        # Симметрично логике build_economic_effect_block в _pack5_blocks.py:91-104:
        # проект учитывается, если plannedValue > 0 OR realizedValue > 0.
        # Используем JSONB-операторы PostgreSQL: ключ "economicEffect" существует,
        # и хотя бы одно из числовых полей > 0.
        ee_key = Project.extra["economicEffect"]
        q = q.where(
            Project.extra.is_not(None),
            ee_key.is_not(None),
            or_(
                ee_key["plannedValue"].as_float() > 0,
                ee_key["realizedValue"].as_float() > 0,
            ),
        )
    if search:
        s = f"%{search.strip().lower()}%"
        q = q.where(or_(
            func.lower(Project.title).like(s),
            func.lower(Project.num).like(s),
            func.lower(Project.assignee_name).like(s),
            func.lower(Project.assignee_email).like(s),
        ))

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    sort_col = {
        "updated_at": Project.updated_at,
        "created_at": Project.created_at,
        "due_date":   Project.due_date,
        "priority":   Project.priority,
        "num":        Project.num,
        "title":      Project.title,
    }.get(sort_by, Project.updated_at)
    q = q.order_by(asc(sort_col).nulls_last() if sort_dir == "asc" else desc(sort_col).nulls_last())
    q = q.limit(limit).offset(offset)

    rows = (await db.execute(q)).all()
    project_ids = [r.Project.id for r in rows]

    # Aggregate child task counts (one batch query)
    child_counts: dict[UUID, dict[str, int]] = {pid: {"total": 0, "done": 0} for pid in project_ids}
    if project_ids:
        cnt_q = (select(Task.project_id, Task.status, func.count())
                 .where(Task.project_id.in_(project_ids), Task.is_archived.is_(False))
                 .group_by(Task.project_id, Task.status))
        for pid, st, cnt in (await db.execute(cnt_q)).all():
            if pid in child_counts:
                child_counts[pid]["total"] += cnt
                if st == "done":
                    child_counts[pid]["done"] = cnt

    items = [
        _project_to_brief(
            r.Project, r.board_name, r.company_code, r.company_name,
            tasks_total=child_counts.get(r.Project.id, {}).get("total", 0),
            tasks_done=child_counts.get(r.Project.id, {}).get("done", 0),
        )
        for r in rows
    ]

    # Aggregates for filter facets (over the same WHERE filters MINUS status/priority)
    facet_q = (select(Project.status, Project.priority)
               .where(Project.is_archived.is_(False)))
    if scope_ids is not None: facet_q = facet_q.where(Project.company_id.in_(scope_ids))
    if portfolio_year: facet_q = facet_q.where(Project.portfolio_year == portfolio_year)
    if company_id:     facet_q = facet_q.where(Project.company_id == company_id)
    if board_id:       facet_q = facet_q.where(Project.board_id == board_id)
    facet_rows = (await db.execute(facet_q)).all()
    by_status:   dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for st, pr in facet_rows:
        by_status[st]   = by_status.get(st, 0) + 1
        by_priority[pr] = by_priority.get(pr, 0) + 1

    # Deferred count — Phase 13
    def_q = (select(func.count()).select_from(Project)
             .where(Project.is_archived.is_(False),
                    Project.linked_year.is_not(None)))
    if scope_ids is not None: def_q = def_q.where(Project.company_id.in_(scope_ids))
    if portfolio_year: def_q = def_q.where(Project.portfolio_year == portfolio_year)
    if company_id:    def_q = def_q.where(Project.company_id == company_id)
    if board_id:      def_q = def_q.where(Project.board_id == board_id)
    by_status['deferred'] = (await db.execute(def_q)).scalar() or 0

    # Available years (for year selector — also scoped)
    yr_q = (select(Project.portfolio_year, func.count())
            .where(Project.portfolio_year.is_not(None), Project.is_archived.is_(False)))
    if scope_ids is not None:
        yr_q = yr_q.where(Project.company_id.in_(scope_ids))
    yr_q = yr_q.group_by(Project.portfolio_year).order_by(Project.portfolio_year.desc())
    available_years = [y for y, _ in (await db.execute(yr_q)).all()]

    return ProjectListResponse(
        items=items, total=total,
        by_status=by_status, by_priority=by_priority,
        available_years=available_years,
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    q = (select(Project,
                Board.name.label("board_name"),
                Company.code.label("company_code"),
                Company.name_short.label("company_name"))
         .outerjoin(Board, Project.board_id == Board.id)
         .outerjoin(Company, Project.company_id == Company.id)
         .where(Project.id == project_id))
    row = (await db.execute(q)).first()
    if not row:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if row.Project.company_id is None or row.Project.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")

    p = row.Project

    # Child task counts
    cnt_q = (select(Task.status, func.count())
             .where(Task.project_id == p.id, Task.is_archived.is_(False))
             .group_by(Task.status))
    counts = dict((await db.execute(cnt_q)).all())
    tasks_total = sum(counts.values())
    tasks_done = counts.get("done", 0)

    base = _project_to_brief(p, row.board_name, row.company_code, row.company_name,
                             tasks_total=tasks_total, tasks_done=tasks_done)
    extra = p.extra or {}
    # Load project comments with author info
    cmt_rows = await db.execute(
        select(ProjectComment).where(ProjectComment.project_id == p.id).order_by(ProjectComment.created_at.desc()).limit(100)
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

    return ProjectDetail(
        **base.model_dump(),
        description=p.description,
        scope=extra.get("scope"),
        consultants=extra.get("consultants", []) or [],
        extra=extra,
        legacy_id=p.legacy_id,
        creator_id=p.creator_id,
        start_date=p.start_date,
        completed_at=p.completed_at,
        consultant_comment=extra.get("consultant_comment"),
        economic_effect=extra.get("economic_effect") if isinstance(extra.get("economic_effect"), dict) else None,
        comments=comments_list,
    )


@router.get("/{project_id}/tasks", response_model=List[TaskBrief])
async def get_project_tasks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all child tasks of this project."""
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.view")

    # First check user can see the parent project
    proj_res = await db.execute(select(Project.company_id).where(Project.id == project_id))
    proj_co = proj_res.scalar_one_or_none()
    if proj_co is None:
        # Project doesn't exist or has no company — for scoped users this is 404 either way
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")
    else:
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and proj_co not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")

    q = (select(Task, Board.name.label("board_name"), Company.code.label("company_code"))
         .outerjoin(Board, Task.board_id == Board.id)
         .outerjoin(Company, Task.company_id == Company.id)
         .where(Task.project_id == project_id, Task.is_archived.is_(False))
         .order_by(Task.priority.asc(), Task.due_date.asc().nulls_last()))
    rows = (await db.execute(q)).all()

    out: list[TaskBrief] = []
    for r in rows:
        t = r.Task
        is_overdue = bool(t.due_date and t.status != "done" and t.due_date < date.today())
        out.append(TaskBrief(
            id=t.id, num=t.num, title=t.title,
            status=t.status, priority=t.priority,
            board_id=t.board_id, board_name=r.board_name,
            company_id=t.company_id, company_code=r.company_code,
            assignee_email=t.assignee_email, assignee_name=t.assignee_name, assignee_id=t.assignee_id,
            due_date=t.due_date, portfolio_year=t.portfolio_year,
            is_project=False,  # tasks endpoint always returns tasks (not projects)
            progress_percent=t.progress_percent,
            is_overdue=is_overdue, tags=t.tags,
            created_at=t.created_at, updated_at=t.updated_at,
        ))
    return out


@router.post("", response_model=ProjectDetail, status_code=http_status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")

    # Per-company scope: scoped users can only create projects for allowed companies
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if payload.company_id is None or payload.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot create project for a company outside your allowed list",
            )

    # Separate monolith-specific fields (live in extra JSONB) from real columns.
    EXTRA_FIELDS = {"consultant", "consultant_comment", "economic_effect", "quarters", "direction", "scope"}
    raw = payload.model_dump(exclude_none=True)
    extra: dict = {}
    for k in list(raw.keys()):
        if k in EXTRA_FIELDS:
            extra[k] = raw.pop(k)

    p = Project(**raw, extra=(extra or None), creator_id=user.id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return await _hydrate_detail(db, p)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.edit")

    res = await db.execute(select(Project).where(Project.id == project_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if p.company_id is None or p.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")
        # Block reassignment to forbidden company
        new_company_id = payload.model_dump(exclude_unset=True).get("company_id")
        if new_company_id is not None and new_company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot reassign project to a company outside your allowed list",
            )

    changes = payload.model_dump(exclude_unset=True)

    # Separate monolith-specific fields and merge into extra JSONB
    EXTRA_FIELDS = {"consultant", "consultant_comment", "economic_effect", "quarters", "direction", "scope"}
    extra_updates = {k: changes.pop(k) for k in list(changes.keys()) if k in EXTRA_FIELDS}

    for field, value in changes.items():
        setattr(p, field, value)

    if extra_updates:
        merged = dict(p.extra or {})
        for k, v in extra_updates.items():
            if v is None:
                merged.pop(k, None)
            else:
                merged[k] = v
        p.extra = merged or None

    if changes.get("status") == "done" and not p.completed_at:
        p.completed_at = datetime.now(timezone.utc)
    if "status" in changes and changes["status"] != "done":
        p.completed_at = None

    await db.commit()
    await db.refresh(p)
    return await _hydrate_detail(db, p)


@router.delete("/{project_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "tasks.delete"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Permission required: tasks.delete")

    res = await db.execute(select(Project).where(Project.id == project_id))
    p = res.scalar_one_or_none()
    if not p:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Project not found")

    # Per-company scope check
    scope_ids = await allowed_company_ids(db, user)
    if scope_ids is not None:
        if p.company_id is None or p.company_id not in scope_ids:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access to this project")

    p.is_archived = True
    await db.commit()



async def _validate_linked_project(
    db: AsyncSession,
    current_project: Project,
    linked_id,
) -> None:
    """Ensure linked_project_id refers to a project in a future year (FY+1 or later)."""
    if not linked_id:
        return
    if not current_project.portfolio_year:
        return
    linked = await db.get(Project, linked_id)
    if not linked:
        raise HTTPException(422, detail="Связанный проект не найден")
    if linked.portfolio_year is None or linked.portfolio_year <= current_project.portfolio_year:
        raise HTTPException(
            422,
            detail=f"Связанный проект должен быть в будущем году. "
                   f"Текущий: FY{current_project.portfolio_year}, указан: FY{linked.portfolio_year}. "
                   f"Перенос разрешён только на FY+1 и далее."
        )

async def _hydrate_detail(db: AsyncSession, p: Project) -> ProjectDetail:
    board_name = company_code = company_name = None
    if p.board_id:
        board_name = (await db.execute(select(Board.name).where(Board.id == p.board_id))).scalar_one_or_none()
    if p.company_id:
        rec = (await db.execute(
            select(Company.code, Company.name_short).where(Company.id == p.company_id)
        )).first()
        if rec:
            company_code, company_name = rec.code, rec.name_short

    cnt_q = (select(Task.status, func.count())
             .where(Task.project_id == p.id, Task.is_archived.is_(False))
             .group_by(Task.status))
    counts = dict((await db.execute(cnt_q)).all())

    base = _project_to_brief(p, board_name, company_code, company_name,
                             tasks_total=sum(counts.values()),
                             tasks_done=counts.get("done", 0))
    extra = p.extra or {}

    # Load project comments with author info (mirrors tasks.py _hydrate_detail)
    cmt_rows = await db.execute(
        select(ProjectComment).where(ProjectComment.project_id == p.id).order_by(ProjectComment.created_at.desc()).limit(100)
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

    return ProjectDetail(
        **base.model_dump(),
        description=p.description,
        scope=extra.get("scope"),
        consultants=extra.get("consultants", []) or [],
        extra=extra,
        legacy_id=p.legacy_id,
        creator_id=p.creator_id,
        start_date=p.start_date,
        completed_at=p.completed_at,
        consultant_comment=extra.get("consultant_comment"),
        economic_effect=extra.get("economic_effect") if isinstance(extra.get("economic_effect"), dict) else None,
        comments=comments_list,
    )
