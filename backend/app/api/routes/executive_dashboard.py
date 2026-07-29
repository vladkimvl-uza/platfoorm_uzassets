"""Executive Dashboard API — thin HTTP layer (refactored 2026-05-25).

Original 480-LOC function split across `ExecDashboardService` (orchestrator
with 12 named stage methods). Pack 4/5 sub-block helpers живут в
`services/exec_dashboard/blocks_pack4.py` / `blocks_pack5.py` /
`drill_pack4.py` (перенесены из routes 2026-06-01 — агрегация в сервисе).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import has_effective_permission
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


async def _require_any(db: AsyncSession, user: User, codes: tuple[str, ...]) -> None:
    for code in codes:
        if await has_effective_permission(db, user, code):
            return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        f"Permission required: {codes[0]}",
    )


# Гейт payload'а экрана министра. До этой правки здесь стоял только
# `get_current_user`: право экрана жило исключительно в meta роута фронта, и
# прямой вызов `GET /dashboard/executive/{year}` отдавал портфельный агрегат
# (KPI, БП, рейтинги, кредиты, закупки, ESG, governance) любому, кто вошёл.
#
# Почему не один exec_dashboard.view. Тот же payload читает /dashboard —
# страница мягкого отказа, которую по ТЗ гейтить нельзя: три её блока
# (ExecDashRatings / ExecDashExecutionChart / ExecDashDirectionsBlock) берут
# данные отсюда, отдельного эндпоинта под них нет. Поэтому дашборд открывает
# payload СВОИМ правом dashboard.view (плюс переходный tasks.view — ровно тот
# же набор, что и у /dashboard/shareholder, иначе страница отказа грузилась бы
# наполовину). Экран министра при этом гейтится своим exec_dashboard.view:
# снятие «Финансов» больше его не открывает и не закрывает.
_EXEC_PAYLOAD_CODES = ("exec_dashboard.view", "dashboard.view", "tasks.view")

# Дрилл направления — общая модалка (DirectionDrillModal): её открывают не
# только с экрана министра, но и с /dashboard (KpiTileDrillModal,
# CompanyTileDrillModal) и с /financials (FinKpiDrillModal). Поэтому к набору
# добавлено financials.view — иначе дрилл с экрана Финансов молча ломался бы у
# пользователя без прав дашборда.
_DIRECTION_DRILL_CODES = _EXEC_PAYLOAD_CODES + ("financials.view",)


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
    await _require_any(db, user, _DIRECTION_DRILL_CODES)
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
    bp_period: Optional[str] = Query(
        None, description="BP tracker period: annual|q1|q2|q3|q4 (default annual)",
    ),
    company: Optional[UUID] = Query(
        None, description="Сузить весь дашборд до одной компании (по её id)",
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
    await _require_any(db, user, _EXEC_PAYLOAD_CODES)
    # Валидируем период BP-трекера: невалидное значение → annual (legacy).
    bp_period_norm = (bp_period or "annual").lower()
    if bp_period_norm not in ("annual", "q1", "q2", "q3", "q4"):
        bp_period_norm = "annual"

    scope = await _scope(db, user)
    # Фокус на одной компании: сужаем ВЕСЬ дашборд через тот же механизм
    # company_id-скоупа, что и RBAC (все блоки уважают scope_company_ids).
    # Соблюдаем RBAC: выбранная компания должна быть в разрешённом наборе.
    effective_scope = scope
    if company is not None:
        if scope is not None and company not in scope:
            effective_scope = []  # компания вне доступа пользователя → пусто
        else:
            effective_scope = [company]
    cache_key = (
        year,
        tuple(sorted(sectors)) if sectors else None,
        bp_metric,
        bp_period_norm,
        str(company) if company else None,
        _scope_sig(effective_scope),
    )
    cached = _dashboard_cache.get(cache_key)
    if cached is not None:
        return cached

    data = await service.build_dashboard(
        year=year, sectors=sectors, bp_metric=bp_metric,
        bp_period=bp_period_norm,
        scope_company_ids=effective_scope,
    )
    _dashboard_cache.set(cache_key, data)
    return data
