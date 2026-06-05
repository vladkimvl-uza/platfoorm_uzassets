"""Projects API — thin HTTP layer (refactored 2026-05-25).

10-layer template: routes → dependencies → services → uow → repositories.

Endpoints (URLs preserved):
  GET    /projects                 list with filters
  GET    /projects/{id}            single project detail (with child task counts)
  GET    /projects/{id}/tasks      child tasks of this project
  POST   /projects                 create
  PATCH  /projects/{id}            update
  POST   /projects/{id}/result     toggle результат flag
  DELETE /projects/{id}            archive
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.dependencies.projects import (
    ProjectsEditorServiceDep,
    ProjectsQueryServiceDep,
)
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectListResponse,
    ProjectUpdate,
)
from app.schemas.task import TaskBrief

router = APIRouter(prefix="/projects", tags=["projects"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"Permission required: {code}")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else None


# ─── Queries ──────────────────────────────────────────────────────

@router.get("", response_model=ProjectListResponse)
async def list_projects(
    service: ProjectsQueryServiceDep,
    portfolio_year: Optional[int] = Query(None, description="Year filter (e.g. 2025/2026)"),
    company_id: Optional[UUID] = Query(None),
    company_code: Optional[str] = Query(None),
    board_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None, pattern="^(init|new|active|review|done|quarterly|monthly|ongoing|deferred)$"),
    direction: Optional[str] = Query(None, description='Filter by direction code'),
    priority: Optional[str] = Query(None, pattern="^(high|medium|low)$"),
    assignee_email: Optional[str] = Query(None),
    only_overdue: bool = Query(False),
    has_economic_effect: bool = Query(False, description="Filter to projects with extra.economicEffect data"),
    search: Optional[str] = Query(None),
    sort_by: str = Query("updated_at", regex="^(updated_at|created_at|due_date|priority|num|title)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List projects (parent containers for tasks). Same RBAC + scoping as tasks.

    Supports filter by company/board/status/priority/direction, search, and a
    `has_economic_effect` switch for finding projects with `extra.economicEffect`."""
    await _require(db, user, "tasks.view")
    return await service.list_projects(
        scope_company_ids=await _scope(db, user),
        portfolio_year=portfolio_year,
        company_id=company_id, company_code=company_code,
        board_id=board_id, status=status, direction=direction,
        priority=priority, assignee_email=assignee_email,
        only_overdue=only_overdue, has_economic_effect=has_economic_effect,
        search=search, sort_by=sort_by, sort_dir=sort_dir,
        limit=limit, offset=offset,
        current_user_id=user.id,
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: UUID,
    service: ProjectsQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.view")
    return await service.get_project(project_id, scope_company_ids=await _scope(db, user))


@router.get("/{project_id}/tasks", response_model=list[TaskBrief])
async def get_project_tasks(
    project_id: UUID,
    service: ProjectsQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.view")
    return await service.get_project_tasks(project_id, scope_company_ids=await _scope(db, user))


# ─── Mutations ────────────────────────────────────────────────────

@router.post("", response_model=ProjectDetail, status_code=http_status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    service: ProjectsEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a project. Requires `tasks.edit` and scope access to `payload.company_id`.

    Scoped users get 403 if `company_id` isn't in their allowed list."""
    await _require(db, user, "tasks.edit")

    scope_ids = await _scope(db, user)
    if scope_ids is not None:
        if payload.company_id is None or payload.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot create project for a company outside your allowed list",
            )

    detail, _info = await service.create_project(payload, creator_id=user.id)
    return detail


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    service: ProjectsEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.edit")
    scope_ids = await _scope(db, user)

    project, info = await service.update_project(
        project_id, payload, scope_company_ids=scope_ids,
    )

    # Side-effect: @-mentions in description
    if info["description_changed"]:
        from app.services.mention_service import notify_mentioned_users
        await notify_mentioned_users(
            db, text=info["description_text"],
            actor_id=user.id,
            actor_name=user.full_name or user.email,
            entity_type="project", entity_id=str(info["project_id"]),
            entity_title=info["project_title"],
            link_url=f"/projects/{info['project_id']}",
        )

    return await service.hydrate_detail(project_id)


@router.post("/{project_id}/result", status_code=http_status.HTTP_200_OK)
async def toggle_project_result(
    project_id: UUID,
    service: ProjectsEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Toggle the «результат» flag on a project."""
    await _require(db, user, "tasks.edit")
    return await service.toggle_result(
        project_id, scope_company_ids=await _scope(db, user),
    )


@router.delete("/{project_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: UUID,
    service: ProjectsEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "tasks.delete")
    await service.archive_project(
        project_id, scope_company_ids=await _scope(db, user),
    )
