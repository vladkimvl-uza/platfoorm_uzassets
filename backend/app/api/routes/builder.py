"""Конструктор проектов и задач — массовое заведение в компаниях.

POST /builder/bulk — создать пачку проектов (с вложенными задачами) и
отдельных задач сразу в НЕСКОЛЬКИХ компаниях, с общими настройками (год,
направление, доска, дедлайн по умолчанию). Переиспользует сервисы создания
задач/проектов (тот же путь, что и одиночное создание), напрямую — bulk-
операция администратора, без модерационного гейта.

Также отдаёт справочники для UI: /builder/companies, /builder/directions.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.dependencies.projects import ProjectsEditorServiceDep
from app.dependencies.tasks import TasksEditorServiceDep
from app.models.company import Company, Direction
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate

router = APIRouter(prefix="/builder", tags=["builder"])


# ─── справочники для UI ────────────────────────────────────────────

@router.get("/companies")
async def builder_companies(db: AsyncSession = Depends(get_db), _u: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Company.id, Company.code, Company.name_short, Company.name_ru).order_by(Company.name_ru),
    )).all()
    return {"items": [
        {"id": str(r._mapping["id"]), "code": r._mapping["code"],
         "name": r._mapping["name_short"] or r._mapping["name_ru"]}
        for r in rows
    ]}


@router.get("/directions")
async def builder_directions(db: AsyncSession = Depends(get_db), _u: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(Direction.id, Direction.code, Direction.name_ru).order_by(Direction.sort_order, Direction.name_ru),
    )).all()
    return {"items": [
        {"id": str(r._mapping["id"]), "code": r._mapping["code"], "name": r._mapping["name_ru"]}
        for r in rows
    ]}


# ─── bulk-схемы ────────────────────────────────────────────────────

class BulkTask(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    status: str = "new"
    priority: str = "medium"
    due_date: Optional[date] = None
    assignee_email: Optional[str] = None
    direction_id: Optional[UUID] = None


class BulkProject(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    status: str = "new"
    priority: str = "medium"
    due_date: Optional[date] = None
    direction_id: Optional[UUID] = None
    tasks: list[BulkTask] = Field(default_factory=list)


class BulkCommon(BaseModel):
    portfolio_year: Optional[int] = None
    direction_id: Optional[UUID] = None       # направление по умолчанию
    board_id: Optional[UUID] = None
    due_date: Optional[date] = None           # дедлайн по умолчанию


class BulkRequest(BaseModel):
    company_ids: list[UUID] = Field(default_factory=list)
    common: BulkCommon = Field(default_factory=BulkCommon)
    projects: list[BulkProject] = Field(default_factory=list)
    standalone_tasks: list[BulkTask] = Field(default_factory=list)


def _pick(*vals):
    for v in vals:
        if v is not None:
            return v
    return None


@router.post("/bulk")
async def bulk_create(
    body: BulkRequest,
    tasks_svc: TasksEditorServiceDep,
    projects_svc: ProjectsEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("tasks.edit")),
):
    """Массовое создание проектов+задач в выбранных компаниях."""
    c = body.common
    targets = body.company_ids or [None]   # если не выбрано — без привязки к компании
    proj_n = 0
    task_n = 0

    for cid in targets:
        # проекты (+ вложенные задачи)
        for p in body.projects:
            pc = ProjectCreate(
                title=p.title, status=p.status, priority=p.priority,
                company_id=cid, portfolio_year=c.portfolio_year, board_id=c.board_id,
                direction_id=_pick(p.direction_id, c.direction_id),
                due_date=_pick(p.due_date, c.due_date),
            )
            detail, _info = await projects_svc.create_project(pc, creator_id=user.id)
            proj_n += 1
            pid = UUID(str(detail.id)) if not isinstance(detail.id, UUID) else detail.id
            for t in p.tasks:
                tc = TaskCreate(
                    title=t.title, status=t.status, priority=t.priority,
                    company_id=cid, project_id=pid, portfolio_year=c.portfolio_year,
                    board_id=c.board_id,
                    direction_id=_pick(t.direction_id, p.direction_id, c.direction_id),
                    due_date=_pick(t.due_date, c.due_date),
                    assignee_email=t.assignee_email,
                )
                await tasks_svc.create_task(tc, creator_id=user.id)
                task_n += 1

        # отдельные задачи (без проекта)
        for t in body.standalone_tasks:
            tc = TaskCreate(
                title=t.title, status=t.status, priority=t.priority,
                company_id=cid, portfolio_year=c.portfolio_year, board_id=c.board_id,
                direction_id=_pick(t.direction_id, c.direction_id),
                due_date=_pick(t.due_date, c.due_date),
                assignee_email=t.assignee_email,
            )
            await tasks_svc.create_task(tc, creator_id=user.id)
            task_n += 1

    return {
        "companies": len([t for t in targets if t is not None]) or 1,
        "projects_created": proj_n,
        "tasks_created": task_n,
    }
