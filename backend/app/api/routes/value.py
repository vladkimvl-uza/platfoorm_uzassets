"""Value Opportunities registry API — реестр возможностей ценности.

Доступ по умолчанию только у владельца (owner обходит проверку прав), но
настраивается: право `value.view` / `value.edit` можно выдать пользователю/группе
через RBAC-админку. Тонкий HTTP-слой, вся логика — в ValueService.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, has_unrestricted_view
from app.core.security import has_effective_permission
from app.dependencies.value import ValueServiceDep
from app.models.user import User
from app.schemas.value import (
    ValueOpportunityCreate,
    ValueOpportunityRead,
    ValueOpportunityUpdate,
    ValueSummary,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/value", tags=["value-opportunities"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"{code} required")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


def _user_name(user: User) -> str:
    return (
        getattr(user, "full_name", None)
        or getattr(user, "email", None)
        or getattr(user, "username", None)
        or "—"
    )


@router.get("", response_model=list[ValueOpportunityRead])
async def list_opportunities(
    service: ValueServiceDep,
    status: Optional[str] = None,
    source: Optional[str] = None,
    company_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "value.view")
    return await service.list(
        status=status, source=source, company_id=company_id,
        scope_company_ids=await _scope(db, user),
    )


@router.get("/summary", response_model=ValueSummary)
async def summary(
    service: ValueServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "value.view")
    return await service.summary(scope_company_ids=await _scope(db, user))


@router.post("/generate")
async def generate_opportunities(
    service: ValueServiceDep,
    request: Request,
    year: int,
    quarter: str = "annual",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Авто-выявление возможностей ценности из детекторов (перерасход к норме +
    отклонения бизнес-плана). Дедуп по fingerprint — повтор не создаёт дублей."""
    await _require(db, user, "value.edit")
    out = await service.generate(
        year=year, quarter=quarter,
        user_id=user.id, user_name=_user_name(user),
        scope_company_ids=await _scope(db, user),
    )
    request.state.activity_summary = (
        f"Авто-выявление возможностей за {year}: создано {out.get('created', 0)}"
    )
    request.state.activity_entity = "Реестр ценности"
    return out


@router.post("", response_model=ValueOpportunityRead)
async def create_opportunity(
    payload: ValueOpportunityCreate,
    service: ValueServiceDep,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "value.edit")
    out = await service.create(payload, user_id=user.id, user_name=_user_name(user))
    request.state.activity_summary = f"Добавлена возможность ценности: {out.title}"
    request.state.activity_entity = "Реестр ценности"
    return out


@router.patch("/{opp_id}", response_model=ValueOpportunityRead)
async def update_opportunity(
    opp_id: UUID,
    payload: ValueOpportunityUpdate,
    service: ValueServiceDep,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "value.edit")
    out = await service.update(opp_id, payload, scope_company_ids=await _scope(db, user))
    if out is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Возможность не найдена")
    request.state.activity_summary = f"Обновлена возможность ценности: {out.title}"
    request.state.activity_entity = "Реестр ценности"
    return out


@router.delete("/{opp_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_opportunity(
    opp_id: UUID,
    service: ValueServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "value.edit")
    ok = await service.delete(opp_id, scope_company_ids=await _scope(db, user))
    if not ok:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Возможность не найдена")
