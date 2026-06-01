"""Consultants & Big-4 dashboard API — thin HTTP layer (refactored 2026-05-25).

Endpoints (URLs preserved):
  GET    /consultants                         list firms (admin)
  POST   /consultants                         create firm
  PATCH  /consultants/{id}                    update firm
  GET    /consultants/{id}/usage              assignments count
  DELETE /consultants/{id}                    soft/hard delete
  GET    /consultants/overview                full dashboard payload
  GET    /consultants/by-company/{co_id}      per-company consultants
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import ensure_company_access
from app.core.security import _has_permission, has_effective_permission
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
    sort_order: int = 999


class ConsultantPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    abbr: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_big4: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


# ─── permission gates ─────────────────────────────────────────────

def _admin_gate(user: User) -> None:
    if user.is_owner:
        return
    if _has_permission(user, "companies.edit") or _has_permission(user, "tasks.manage"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: companies.edit or tasks.manage",
    )


# ─── list / CRUD ──────────────────────────────────────────────────

@router.get("")
async def list_consultants(
    service: ConsultantsServiceDep,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    return await service.list_consultants(include_inactive=include_inactive)


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_consultant(
    payload: ConsultantIn,
    service: ConsultantsServiceDep,
    user: User = Depends(get_current_user),
):
    _admin_gate(user)
    return await service.create_consultant(payload=payload)


@router.patch("/{consultant_id}")
async def update_consultant(
    consultant_id: UUID,
    payload: ConsultantPatch,
    service: ConsultantsServiceDep,
    user: User = Depends(get_current_user),
):
    _admin_gate(user)
    return await service.update_consultant(consultant_id, payload=payload)


@router.get("/{consultant_id}/usage")
async def consultant_usage(
    consultant_id: UUID,
    service: ConsultantsServiceDep,
    user: User = Depends(get_current_user),
):
    _admin_gate(user)
    return await service.consultant_usage(consultant_id)


@router.delete("/{consultant_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_consultant(
    consultant_id: UUID,
    service: ConsultantsServiceDep,
    hard: bool = False,
    user: User = Depends(get_current_user),
):
    _admin_gate(user)
    await service.delete_consultant(consultant_id, hard=hard)


# ─── overview dashboard ───────────────────────────────────────────

@router.get("/overview")
async def consultants_overview(
    service: ConsultantsServiceDep,
    year: Optional[int] = Query(None, description="Portfolio year filter; default = all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    return await service.overview(year=year)


# ─── per-company ──────────────────────────────────────────────────

@router.get("/by-company/{company_id}")
async def consultants_by_company(
    company_id: UUID,
    service: ConsultantsServiceDep,
    year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if not await has_effective_permission(db, user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    await ensure_company_access(db, user, company_id)
    return await service.by_company(company_id, year=year)
