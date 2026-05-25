"""Shareholder Dashboard API — thin HTTP layer (refactored 2026-05-25).

3 endpoints split across DashboardService:
  - shareholder_dashboard: full payload (kpis, statuses, sectors,
    directions, ratings, completion chart)
  - kpi_drill: per-bucket × entity drill grouped by company
  - company_drill: single-company flat list of projects+tasks
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import has_effective_permission
from app.dependencies.dashboard import DashboardServiceDep
from app.models.user import User


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


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
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    return await service.shareholder_dashboard(
        year=year, sector_code=sector_code,
        direction_code=direction_code, company_code=company_code,
    )


@router.get("/kpi-drill")
async def kpi_tile_drill(
    service: DashboardServiceDep,
    bucket: str = Query(..., regex="^(total|done|active|overdue|deferred)$"),
    entity: str = Query("tasks", regex="^(projects|tasks)$"),
    year: Optional[int] = Query(None),
    sector_code: Optional[str] = Query(None),
    direction_code: Optional[str] = Query(None),
    company_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """KPI-tile drill-down (Pack 7.46): nested response grouped by company."""
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    return await service.kpi_drill(
        bucket=bucket, entity=entity, year=year,
        sector_code=sector_code,
        direction_code=direction_code,
        company_code=company_code,
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
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    return await service.company_drill(company_code=company_code, year=year)
