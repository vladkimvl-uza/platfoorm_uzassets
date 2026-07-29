"""Executive Overview — министерский обзор сектор→компания→проекты+дедлайны.

Доступ по скоупу (как Executive Dashboard): owner/unrestricted видит весь
портфель, scoped-пользователь — только разрешённые компании.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import (
    allowed_company_ids,
    ensure_company_access,
    has_unrestricted_view,
)
from app.core.security import has_effective_permission
from app.models.project import Project
from app.models.user import User
from app.schemas.exec_overview import ExecOverviewResponse, ExecOverviewTask
from app.services.exec_overview import build_exec_overview, build_project_tasks

log = logging.getLogger(__name__)
router = APIRouter(prefix="/exec-overview", tags=["exec-overview"])


async def _scope(db: AsyncSession, user: User):
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


async def _require_exec_overview(db: AsyncSession, user: User) -> None:
    """Гейт модуля «Сводный обзор портфеля».

    Роут фронта раньше требовал projects.view — кода, которого нет в каталоге,
    поэтому экран не открывался никому, кроме owner/admin. Бэкенд же не
    проверял НИЧЕГО: обзор всего портфеля (проекты, дедлайны, выручка/прибыль,
    ключевые результаты БП) отдавался любому вошедшему прямым вызовом
    `GET /exec-overview`. Теперь оба конца цепочки спрашивают один и тот же
    exec_overview.view.

    Дополнительных фолбэков нет намеренно: обзор читают ровно две поверхности —
    /executive-overview и подвкладка «Сводный обзор» в карточке компании, и обе
    гейтятся этим же правом. Скоуп по компаниям (_scope) остаётся сверху: право
    решает «пускать ли в модуль», скоуп — «чьи данные показать».
    """
    if not await has_effective_permission(db, user, "exec_overview.view"):
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Permission required: exec_overview.view",
        )


@router.get("", response_model=ExecOverviewResponse)
async def exec_overview(
    year: Optional[int] = Query(None, description="Портфельный год (по умолчанию все)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExecOverviewResponse:
    await _require_exec_overview(db, user)
    scope = await _scope(db, user)
    # Ключевые результаты бизнес-плана за Q1 видны при праве bp.view, рейтинги — при
    # ratings.view (owner/admin — bypass). Проекты/дедлайны/«ход проекта» — всем по scope.
    can_bp = has_unrestricted_view(user) or await has_effective_permission(db, user, "bp.view")
    can_ratings = has_unrestricted_view(user) or await has_effective_permission(db, user, "ratings.view")
    return await build_exec_overview(
        db, scope, year, date.today(), can_bp=can_bp, can_ratings=can_ratings,
    )


@router.get("/projects/{project_id}/tasks", response_model=list[ExecOverviewTask])
async def project_tasks(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ExecOverviewTask]:
    # Раскрытие проекта — часть того же экрана, поэтому право то же: без этой
    # проверки задачи проекта тянулись бы в обход гейта модуля.
    await _require_exec_overview(db, user)
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Проект не найден")
    if proj.company_id:
        await ensure_company_access(db, user, proj.company_id)
    return await build_project_tasks(db, project_id, date.today())
