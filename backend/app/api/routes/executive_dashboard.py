"""Executive Dashboard API — thin HTTP layer (refactored 2026-05-25).

Original 480-LOC function split across `ExecDashboardService` (orchestrator
with 12 named stage methods). Pack 4/5 sub-block helpers живут в
`services/exec_dashboard/blocks_pack4.py` / `blocks_pack5.py` /
`drill_pack4.py` (перенесены из routes 2026-06-01 — агрегация в сервисе).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.dependencies.exec_dashboard import ExecDashboardServiceDep
from app.models.user import User
from app.schemas.executive_dashboard import (
    ExecDirectionDrillResponse,
    ExecutiveDashboardData,
)

router = APIRouter(prefix="/dashboard/executive", tags=["dashboard"])


async def _scope(db: AsyncSession, user: User):
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


# Pack 7.36 — must register BEFORE /{year} so path param doesn't shadow it
@router.get(
    "/directions/{direction_code}",
    response_model=ExecDirectionDrillResponse,
)
async def direction_drill(
    direction_code: str,
    service: ExecDashboardServiceDep,
    year: Optional[int] = Query(None, description="Filter by portfolio_year"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Drill-down breakdown for a single business direction (mining, oilgas, etc.).

    Returns per-company task/project rollup + KPI completion within that
    direction. Used by the Executive Dashboard direction-tile click-through."""
    return await service.direction_drill(
        direction_code, year=year,
        scope_company_ids=await _scope(db, user),
    )


@router.get("/{year}", response_model=ExecutiveDashboardData)
async def executive_dashboard(
    year: int,
    service: ExecDashboardServiceDep,
    sectors: Optional[list[str]] = Query(
        None,
        description="Filter: ['mining','oilgas',...] (normalized in service)",
    ),
    bp_metric: Optional[str] = Query(
        None, description="BP tracker metric: revenue|ebitda|profit",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full Executive Dashboard payload: KPI summary, BP tracker, ratings,
    credit portfolio, procurement, ESG, governance — all aggregated server-side.

    Single-call API for the home screen. RBAC-scoped: scoped users see only
    their allowed companies in every block. `sectors` filter limits aggregation
    to those domain sectors; `bp_metric` switches the BP-tracker headline metric."""
    return await service.build_dashboard(
        year=year, sectors=sectors, bp_metric=bp_metric,
        scope_company_ids=await _scope(db, user),
    )
