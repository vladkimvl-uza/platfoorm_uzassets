"""Executive Overview — министерский обзор сектор→компания→проекты+дедлайны.

Доступ по скоупу (как Executive Dashboard): owner/unrestricted видит весь
портфель, scoped-пользователь — только разрешённые компании.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.models.user import User
from app.schemas.exec_overview import ExecOverviewResponse
from app.services.exec_overview import build_exec_overview

router = APIRouter(prefix="/exec-overview", tags=["exec-overview"])


async def _scope(db: AsyncSession, user: User):
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


@router.get("", response_model=ExecOverviewResponse)
async def exec_overview(
    year: Optional[int] = Query(None, description="Портфельный год (по умолчанию все)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExecOverviewResponse:
    scope = await _scope(db, user)
    return await build_exec_overview(db, scope, year, date.today())
