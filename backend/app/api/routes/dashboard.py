"""Shareholder Dashboard API — thin HTTP layer (refactored 2026-05-25).

3 endpoints split across DashboardService:
  - shareholder_dashboard: full payload (kpis, statuses, sectors,
    directions, ratings, completion chart)
  - kpi_drill: per-bucket × entity drill grouped by company
  - company_drill: single-company flat list of projects+tasks
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import has_effective_permission
from app.dependencies.dashboard import DashboardServiceDep
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _require_dashboard_view(db: AsyncSession, user: User) -> None:
    """Гейт данных дашборда акционера.

    `dashboard.view` до этой правки не проверялось нигде — ни на фронте, ни на
    бэке; выдача права ничего не меняла. Теперь право открывает дашборд само по
    себе (пользователь только с dashboard.view получает сводку, раньше — нет).

    Фолбэк на `tasks.view` убран (29.07.2026): пока он существовал, снятие
    «Дашборда» в сетке доступа ничего не меняло — экран открывался по праву
    задач. Право роздано ролям разовой миграцией `_patch_dashboard_view_grant`,
    а мягкий отказ роутера теперь ведёт на /home, а не на дашборд, поэтому
    жёсткий 403 здесь тупиком не становится."""
    if await has_effective_permission(db, user, "dashboard.view"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: dashboard.view",
    )


@router.get("/shareholder")
async def shareholder_dashboard(
    service: DashboardServiceDep,
    year: Optional[int] = Query(None),
    sector_code: Optional[str] = Query(None),
    direction_code: Optional[str] = Query(None),
    company_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    await _require_dashboard_view(db, user)
    # RBAC scope: ограниченный пользователь видит счётчики только своих компаний.
    scope = None if has_unrestricted_view(user) else (await allowed_company_ids(db, user) or [])
    return await service.shareholder_dashboard(
        year=year, sector_code=sector_code,
        direction_code=direction_code, company_code=company_code,
        scope_company_ids=scope,
    )


@router.get("/kpi-drill")
async def kpi_tile_drill(
    service: DashboardServiceDep,
    # status:<код> — разрез кольца «Статусы» (init/new/active/review/done/
    # quarterly/monthly/ongoing); остальные — сводные бакеты KPI-плиток.
    bucket: str = Query(
        ...,
        regex="^(total|done|active|overdue|deferred|status:[a-z_]{2,24})$",
    ),
    entity: str = Query("tasks", regex="^(projects|tasks)$"),
    year: Optional[int] = Query(None),
    sector_code: Optional[str] = Query(None),
    direction_code: Optional[str] = Query(None),
    company_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """KPI-tile drill-down (Pack 7.46): nested response grouped by company."""
    await _require_dashboard_view(db, user)
    scope = None if has_unrestricted_view(user) else (await allowed_company_ids(db, user) or [])
    return await service.kpi_drill(
        bucket=bucket, entity=entity, year=year,
        sector_code=sector_code,
        direction_code=direction_code,
        company_code=company_code,
        scope_company_ids=scope,
    )


@router.get("/company-drill")
async def company_tile_drill(
    service: DashboardServiceDep,
    company_code: str = Query(...),
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Single-company drill (Pack 7.47): flat projects + tasks list."""
    await _require_dashboard_view(db, user)
    scope = None if has_unrestricted_view(user) else (await allowed_company_ids(db, user) or [])
    return await service.company_drill(
        company_code=company_code, year=year, scope_company_ids=scope,
    )
