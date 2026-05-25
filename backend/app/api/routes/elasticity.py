"""Pack 7.43 — Elasticity & project effects API — thin HTTP shim
(refactored 2026-05-25)."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.dependencies.elasticity import ElasticityServiceDep
from app.models.user import User
from app.schemas.elasticity import (
    DecompositionResult, ElasticityRead, ElasticityUpsert,
    ProjectEffectRead, ProjectEffectUpsert,
)


router = APIRouter(prefix="/elasticity", tags=["elasticity"])


# ─── Constants ────────────────────────────────────────────────────

@router.get("/constants")
async def get_constants(
    service: ElasticityServiceDep,
    _u: User = Depends(get_current_user),
):
    return await service.constants()


# ─── Elasticity CRUD ──────────────────────────────────────────────

@router.get("/coefficients", response_model=List[ElasticityRead])
async def list_coefficients(
    service: ElasticityServiceDep,
    scenario_id: Optional[PyUUID] = Query(None),
    company_id: Optional[PyUUID] = Query(None),
    include_global: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
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
    return await service.upsert_coefficient(payload, db, user)


@router.delete("/coefficients/{coef_id}")
async def delete_coefficient(
    coef_id: PyUUID,
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.delete_coefficient(coef_id, db, user)


# ─── Project effects CRUD ─────────────────────────────────────────

@router.get("/project-effects", response_model=List[ProjectEffectRead])
async def list_project_effects(
    service: ElasticityServiceDep,
    project_id: Optional[PyUUID] = Query(None),
    effective_year: Optional[int] = Query(None),
    target_metric: Optional[str] = Query(None),
    company_id: Optional[PyUUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(get_current_user),
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
    return await service.upsert_project_effect(payload, db, user)


@router.delete("/project-effects/{effect_id}")
async def delete_project_effect(
    effect_id: PyUUID,
    service: ElasticityServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
    _u: User = Depends(get_current_user),
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
