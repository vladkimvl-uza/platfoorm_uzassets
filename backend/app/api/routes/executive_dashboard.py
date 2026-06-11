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
from app.core.ttl_cache import TTLCache
from app.dependencies.exec_dashboard import ExecDashboardServiceDep
from app.models.user import User
from app.schemas.executive_dashboard import (
    ExecDirectionDrillResponse,
    ExecutiveDashboardData,
)

router = APIRouter(prefix="/dashboard/executive", tags=["dashboard"])

# Тяжёлый агрегат (12 стадий) + лендинг owner'а → кешируем на 60с.
# Ключ ОБЯЗАТЕЛЬНО включает scope, иначе scoped-юзер получит чужой портфель.
_DASHBOARD_TTL_SECONDS = 60
_dashboard_cache = TTLCache(ttl_seconds=_DASHBOARD_TTL_SECONDS)


def _scope_sig(scope: Optional[list]) -> str:
    """Стабильная подпись scope для ключа кеша. None (unrestricted) ≠ [] (нет компаний)."""
    if scope is None:
        return "all"
    return ",".join(sorted(str(s) for s in scope))


async def _scope(db: AsyncSession, user: User):
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


# must register BEFORE /{year} so path param doesn't shadow it
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
    to those domain sectors; `bp_metric` switches the BP-tracker headline metric.

    Кешируется на 60с по (year, sectors, bp_metric, scope) — owner/admin
    (unrestricted) делят одну запись, поэтому повторные открытия/обновления
    лендинга не пересчитывают 12 стадий заново."""
    scope = await _scope(db, user)
    cache_key = (
        year,
        tuple(sorted(sectors)) if sectors else None,
        bp_metric,
        _scope_sig(scope),
    )
    cached = _dashboard_cache.get(cache_key)
    if cached is not None:
        return cached

    data = await service.build_dashboard(
        year=year, sectors=sectors, bp_metric=bp_metric,
        scope_company_ids=scope,
    )
    _dashboard_cache.set(cache_key, data)
    return data
