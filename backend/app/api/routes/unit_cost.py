"""Удельная себестоимость — API (тонкий слой над UnitCostService).

Права: `unit_cost.view` — чтение обзора, `unit_cost.edit` — правка цен
энергоносителей и данных компании. Раньше здесь стояли financials.view /
financials.edit: экран не имел собственного права, и «Финансы» открывали его
заодно. Теперь гейт совпадает с маршрутом фронта (`/unit-cost`) и вкладкой
«Себестоимость» в карточке компании — иначе право было бы только на фронте,
а прямой вызов API обходил бы его.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.models.user import User
from app.services.unit_cost.service import UnitCostService

router = APIRouter(prefix="/unit-cost", tags=["unit-cost"])


@router.get("/overview")
async def unit_cost_overview(
    year: int = Query(2025, ge=2018, le=2035),
    quarter: str = Query("annual", pattern="^(annual|q1|q2|q3|q4)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "unit_cost.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "unit_cost.view required")
    scope_ids = await allowed_company_ids(db, user)
    return await UnitCostService().overview(db, year=year, quarter=quarter, scope_ids=scope_ids)


class PricesPayload(BaseModel):
    prices: dict[str, Any] = {}
    world: dict[str, Any] = {}


@router.put("/prices")
async def unit_cost_save_prices(
    payload: PricesPayload,
    year: int = Query(2025, ge=2018, le=2035),
    quarter: str = Query("annual", pattern="^(annual|q1|q2|q3|q4)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "unit_cost.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "unit_cost.edit required")
    # цены — глобальные: менять может только полный доступ к портфелю
    if await allowed_company_ids(db, user) is not None:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN,
                            "Цены энергоносителей — только для полного доступа к портфелю")
    return await UnitCostService().save_prices(
        db, payload.prices, payload.world, year=year, quarter=quarter,
        user_email=user.email, user_id=str(user.id) if user.id else None,
    )


class CompanyPayload(BaseModel):
    products: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    comments: list[dict[str, Any]] = []


@router.put("/companies/{code}")
async def unit_cost_save_company(
    code: str,
    payload: CompanyPayload,
    year: int = Query(2025, ge=2018, le=2035),
    quarter: str = Query("annual", pattern="^(annual|q1|q2|q3|q4)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "unit_cost.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "unit_cost.edit required")
    scope_ids = await allowed_company_ids(db, user)
    in_scope = True
    if scope_ids is not None:
        crow = (await db.execute(text(
            "SELECT id FROM companies WHERE code = :c AND is_active = true"
        ), {"c": code})).first()
        in_scope = bool(crow) and crow[0] in set(scope_ids)
    return await UnitCostService().save_company(
        db, code, payload.products, payload.imports, payload.comments,
        year=year, quarter=quarter, cid_in_scope=in_scope,
        user_email=user.email, user_id=str(user.id) if user.id else None,
    )
