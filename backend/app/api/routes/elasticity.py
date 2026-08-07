"""Pack 7.43 — Elasticity & project effects API — thin HTTP shim
(refactored 2026-05-25)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import require_permission
from app.dependencies.elasticity import ElasticityServiceDep
from app.models.user import User
from app.repositories.elasticity_repository import ElasticityRepository
from app.schemas.elasticity import (
    DecompositionResult,
    ElasticityRead,
    ElasticityUpsert,
    ProjectEffectRead,
    ProjectEffectUpsert,
)
from app.services import moderation_service
from app.services.elasticity.service import _admin_only

router = APIRouter(prefix="/elasticity", tags=["elasticity"])


async def _project_company_id(db: AsyncSession, project_id) -> object | None:
    """Компания проектного эффекта — через его проект (для scope-модерации)."""
    from app.models.project import Project
    return (await db.execute(
        select(Project.company_id).where(Project.id == project_id),
    )).scalar_one_or_none()


# ─── Constants ────────────────────────────────────────────────────

@router.get("/constants")
async def get_constants(
    service: ElasticityServiceDep,
    _u: User = Depends(require_permission("finmodel.view")),
):
    return await service.constants()


# ─── Elasticity CRUD ──────────────────────────────────────────────

@router.get("/coefficients", response_model=list[ElasticityRead])
async def list_coefficients(
    service: ElasticityServiceDep,
    scenario_id: Optional[PyUUID] = Query(None),
    company_id: Optional[PyUUID] = Query(None),
    include_global: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("finmodel.view")),
):
    return await service.list_coefficients(
        db, scenario_id=scenario_id, company_id=company_id,
        include_global=include_global,
    )


@router.put("/coefficients", response_model=ElasticityRead)
async def upsert_coefficient(
    payload: ElasticityUpsert,
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Право автора (то же, что применит сервис) проверяем ДО гейта: внешний
    # не-админ получит 403 сразу и НЕ поставит правку вне своего доступа в очередь.
    _admin_only(user)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="elasticity", action="edit",
        entity_id=None,
        entity_label="Коэффициент эластичности",
        company_id=payload.company_id, sector_id=None, year=None,
        payload={**payload.model_dump(mode="json"), "_kind": "coefficient"},
        diff_summary=(
            f"Эластичность {payload.macro_factor}→{payload.target_metric} = {payload.beta}"
        ),
    )
    if queued:
        return JSONResponse(status_code=202, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status,
        })
    return await service.upsert_coefficient(payload, db, user)


@router.delete("/coefficients/{coef_id}")
async def delete_coefficient(
    coef_id: PyUUID,
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    obj = await ElasticityRepository(db).get_coefficient(coef_id)
    company_id = obj.company_id if obj is not None else None
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="elasticity", action="delete",
        entity_id=str(coef_id),
        entity_label="Коэффициент эластичности",
        company_id=company_id, sector_id=None, year=None,
        payload={"_kind": "coefficient", "id": str(coef_id)},
        diff_summary="Удаление коэффициента эластичности",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    return await service.delete_coefficient(coef_id, db, user)


# ─── Project effects CRUD ─────────────────────────────────────────

@router.get("/project-effects", response_model=list[ProjectEffectRead])
async def list_project_effects(
    service: ElasticityServiceDep,
    project_id: Optional[PyUUID] = Query(None),
    effective_year: Optional[int] = Query(None),
    target_metric: Optional[str] = Query(None),
    company_id: Optional[PyUUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("finmodel.view")),
):
    return await service.list_project_effects(
        db,
        project_id=project_id, effective_year=effective_year,
        target_metric=target_metric, company_id=company_id,
    )


@router.put("/project-effects", response_model=ProjectEffectRead)
async def upsert_project_effect(
    payload: ProjectEffectUpsert,
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    company_id = await _project_company_id(db, payload.project_id)
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="elasticity", action="edit",
        entity_id=None,
        entity_label="Эффект проекта",
        company_id=company_id, sector_id=None, year=payload.effective_year,
        payload={**payload.model_dump(mode="json"), "_kind": "project_effect"},
        diff_summary=(
            f"Эффект проекта {payload.target_metric} за {payload.effective_year}"
        ),
    )
    if queued:
        return JSONResponse(status_code=202, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status,
        })
    return await service.upsert_project_effect(payload, db, user)


@router.delete("/project-effects/{effect_id}")
async def delete_project_effect(
    effect_id: PyUUID,
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    obj = await ElasticityRepository(db).get_project_effect(effect_id)
    company_id = (
        await _project_company_id(db, obj.project_id) if obj is not None else None
    )
    queued, sub = await moderation_service.gate_or_apply(
        db, user=user, module="elasticity", action="delete",
        entity_id=str(effect_id),
        entity_label="Эффект проекта",
        company_id=company_id, sector_id=None, year=None,
        payload={"_kind": "project_effect", "id": str(effect_id)},
        diff_summary="Удаление эффекта проекта",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    return await service.delete_project_effect(effect_id, db, user)


# ─── Decomposition ────────────────────────────────────────────────

@router.get("/decomposition", response_model=DecompositionResult)
async def get_decomposition(
    service: ElasticityServiceDep,
    scenario_id: PyUUID = Query(...),
    target_metric: str = Query(...),
    target_year: int = Query(..., ge=2020, le=2050),
    company_id: Optional[PyUUID] = Query(None),
    base_year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("finmodel.view")),
):
    return await service.decomposition(
        db,
        scenario_id=scenario_id, target_metric=target_metric,
        target_year=target_year, company_id=company_id,
        base_year=base_year,
    )


# ─── Admin: apply migrations + seed defaults ─────────────────────

@router.post("/_apply-migrations")
async def apply_migrations_endpoint(
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.apply_migrations(db, user)
