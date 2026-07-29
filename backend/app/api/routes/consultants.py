"""Consultants & Big-4 dashboard API — thin HTTP layer (refactored 2026-05-25).

Endpoints (URLs preserved):
  GET    /consultants                         list firms (admin)
  POST   /consultants                         create firm
  PATCH  /consultants/{id}                    update firm
  GET    /consultants/{id}/usage              assignments count
  DELETE /consultants/{id}                    soft/hard delete
  GET    /consultants/overview                full dashboard payload
  GET    /consultants/by-company/{co_id}      per-company consultants

Права: модульные данные (`/overview`, `/by-company/{id}`) — `consultants.view`;
справочник (`GET /consultants`) — `consultants.view` ИЛИ `tasks.view`, т.к. он
подставляется в редакторе задач и в карточке компании, а не только на экране
модуля; CRUD справочника — `consultants.edit` (или прежние companies.edit /
tasks.manage).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access
from app.core.security import has_effective_permission
from app.dependencies.consultants import ConsultantsServiceDep
from app.models.user import User

router = APIRouter(prefix="/consultants", tags=["consultants"])


# ─── pydantic ─────────────────────────────────────────────────────

class ConsultantIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: Optional[str] = Field(None, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    abbr: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_big4: bool = False
    is_active: bool = True
    sort_order: int = Field(999, ge=0)


class ConsultantPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    abbr: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_big4: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)


# ─── permission gates ─────────────────────────────────────────────

async def _admin_gate(db: AsyncSession, user: User) -> None:
    """CRUD-гейт справочника консультантов. has_effective_permission учитывает
    GroupPermissionGrant (синхронный _has_permission — нет), поэтому право,
    выданное через группу, теперь тоже работает.

    `consultants.edit` добавлено в список: в каталоге право есть и в сетке
    «Доступ к модулям» его видно, но до этой правки оно не проверялось нигде —
    администратор выдавал его и не получал никакого эффекта. Прежние
    companies.edit / tasks.manage сохранены, чтобы не отобрать доступ у тех,
    кто правит справочник сегодня."""
    if user.is_owner:
        return
    if (await has_effective_permission(db, user, "consultants.edit")
            or await has_effective_permission(db, user, "companies.edit")
            or await has_effective_permission(db, user, "tasks.manage")):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: consultants.edit or companies.edit",
    )


async def _require_consultants_view(db: AsyncSession, user: User) -> None:
    """Гейт данных модуля «Консультанты». Раньше здесь стоял `tasks.view`:
    право `consultants.view` проверял только роут фронта, и прямой вызов API
    отдавал сводку любому, кто видит задачи."""
    if not await has_effective_permission(db, user, "consultants.view"):
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Permission required: consultants.view",
        )


# ─── list / CRUD ──────────────────────────────────────────────────

@router.get("")
async def list_consultants(
    service: ConsultantsServiceDep,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    # Справочник, а не данные модуля: список подставляется в редакторе задач,
    # в карточке компании и в каталогах. Поэтому tasks.view остаётся достаточным,
    # но и собственное право модуля тоже открывает справочник — иначе владелец
    # только consultants.view не смог бы прочитать даже названия фирм.
    if not (await has_effective_permission(db, user, "consultants.view")
            or await has_effective_permission(db, user, "tasks.view")):
        raise HTTPException(
            http_status.HTTP_403_FORBIDDEN,
            "Permission required: consultants.view or tasks.view",
        )
    return await service.list_consultants(include_inactive=include_inactive)


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_consultant(
    payload: ConsultantIn,
    service: ConsultantsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _admin_gate(db, user)
    return await service.create_consultant(payload=payload)


@router.patch("/{consultant_id}")
async def update_consultant(
    consultant_id: UUID,
    payload: ConsultantPatch,
    service: ConsultantsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _admin_gate(db, user)
    return await service.update_consultant(consultant_id, payload=payload)


@router.get("/{consultant_id}/usage")
async def consultant_usage(
    consultant_id: UUID,
    service: ConsultantsServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _admin_gate(db, user)
    return await service.consultant_usage(consultant_id)


@router.delete("/{consultant_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_consultant(
    consultant_id: UUID,
    service: ConsultantsServiceDep,
    hard: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _admin_gate(db, user)
    await service.delete_consultant(consultant_id, hard=hard)


# ─── overview dashboard ───────────────────────────────────────────

@router.get("/overview")
async def consultants_overview(
    service: ConsultantsServiceDep,
    year: Optional[int] = Query(None, description="Portfolio year filter; default = all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_consultants_view(db, user)
    # per-company scope (P0): company-scoped юзер видит только свои компании.
    scope = await allowed_company_ids(db, user)  # None=все, []=нет, [ids]=фильтр
    return await service.overview(year=year, allowed_company_ids=scope)


# ─── per-company ──────────────────────────────────────────────────

@router.get("/by-company/{company_id}")
async def consultants_by_company(
    company_id: UUID,
    service: ConsultantsServiceDep,
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    await _require_consultants_view(db, user)
    # Скоуп по компании не трогаем: право открывает модуль, скоуп — конкретную
    # компанию.
    await ensure_company_access(db, user, company_id)
    return await service.by_company(company_id, year=year)
