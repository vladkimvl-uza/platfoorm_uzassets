"""Subsidies registry routes — реестр субсидий по компаниям портфеля.

Метрика «Субсидии» в модуле финансы; клик открывает реестр с фильтрами по
секторам/компаниям. Gated финансовыми правами (financials.view / financials.edit).

Endpoints:
  GET    /subsidies            — реестр (year/sector_code/company_id, scope)
  GET    /subsidies/summary    — агрегаты (для метрики-карточки)
  POST   /subsidies            — создать запись
  PUT    /subsidies/{id}       — обновить запись
  DELETE /subsidies/{id}       — удалить запись
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.core.security import has_effective_permission
from app.models.subsidies import Subsidy
from app.models.user import User
from app.schemas.subsidies import (
    SubsidyPatch,
    SubsidyRow,
    SubsidySummary,
    SubsidyUpsert,
)
from app.services import moderation_service
from app.services.subsidies.service import SubsidiesService

router = APIRouter(prefix="/subsidies", tags=["subsidies"])


async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"Permission required: {code}")


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    if has_unrestricted_view(user):
        return None
    return list(await allowed_company_ids(db, user))


# ─── GET /subsidies ───────────────────────────────────────────────

@router.get("", response_model=list[SubsidyRow])
async def list_subsidies(
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    company_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SubsidyRow]:
    """Реестр субсидий (RBAC-scoped). Фильтры: year / sector_code / company_id."""
    await _require(db, user, "financials.view")
    if company_id is not None:
        await ensure_company_access(db, user, company_id)
    scope = await _scope(db, user)
    return await SubsidiesService(db).list_rows(
        year=year, sector_code=sector_code, company_id=company_id, scope_ids=scope,
    )


# ─── GET /subsidies/summary ───────────────────────────────────────

@router.get("/summary", response_model=SubsidySummary)
async def subsidies_summary(
    year: Optional[int] = None,
    sector_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubsidySummary:
    """Агрегаты по субсидиям (для метрики-карточки в финансах)."""
    await _require(db, user, "financials.view")
    scope = await _scope(db, user)
    return await SubsidiesService(db).summary(year=year, sector_code=sector_code, scope_ids=scope)


# ─── POST /subsidies ──────────────────────────────────────────────

@router.post("", response_model=SubsidyRow, status_code=http_status.HTTP_201_CREATED)
async def create_subsidy(
    payload: SubsidyUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubsidyRow:
    await _require(db, user, "financials.edit")
    # Author scope BEFORE gating: внешний автор не может поставить в очередь
    # правку по компании вне своей области.
    await ensure_company_access(db, user, payload.company_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="subsidies", action="create",
        entity_id=None,
        entity_label=(payload.program or "Субсидия"),
        company_id=payload.company_id, sector_id=None, year=payload.year,
        payload=payload.model_dump(mode="json"),
        diff_summary="Создание записи субсидии",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )
    scope = await _scope(db, user)
    return await SubsidiesService(db).create(payload, user, scope_ids=scope)


# ─── PUT /subsidies/{id} ──────────────────────────────────────────

@router.put("/{subsidy_id}", response_model=SubsidyRow)
async def update_subsidy(
    subsidy_id: UUID,
    patch: SubsidyPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SubsidyRow:
    await _require(db, user, "financials.edit")
    # Resolve + scope-check the target BEFORE gating (mirror companies.py):
    # external author cannot queue an edit outside their company access.
    existing = await db.get(Subsidy, subsidy_id)
    if existing is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Subsidy not found")
    await ensure_company_access(db, user, existing.company_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="subsidies", action="edit",
        entity_id=str(subsidy_id),
        entity_label=(existing.program or "Субсидия"),
        company_id=existing.company_id, sector_id=None, year=existing.year,
        # exclude_unset: иначе одобрение частичной правки занулит неприсланные
        # поля (хендлер ревалидирует и service.update делает exclude_unset).
        payload=patch.model_dump(mode="json", exclude_unset=True),
        diff_summary="Изменение записи субсидии",
    )
    if queued:
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"queued": True, "submission_id": str(sub.id), "status": sub.status},
        )
    scope = await _scope(db, user)
    return await SubsidiesService(db).update(subsidy_id, patch, scope_ids=scope)


# ─── DELETE /subsidies/{id} ───────────────────────────────────────

@router.delete("/{subsidy_id}")
async def delete_subsidy(
    subsidy_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    await _require(db, user, "financials.edit")
    # Resolve + scope-check the target BEFORE gating (mirror companies.py):
    # external author cannot queue a delete outside their company access.
    existing = await db.get(Subsidy, subsidy_id)
    if existing is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Subsidy not found")
    await ensure_company_access(db, user, existing.company_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="subsidies", action="delete",
        entity_id=str(subsidy_id),
        entity_label=(existing.program or "Субсидия"),
        company_id=existing.company_id, sector_id=None, year=existing.year,
        payload={"id": str(subsidy_id)},
        diff_summary="Удаление записи субсидии",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    scope = await _scope(db, user)
    await SubsidiesService(db).delete(subsidy_id, scope_ids=scope)
    return {"ok": True}
