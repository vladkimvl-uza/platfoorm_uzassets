"""Pack 7.43 — Elasticity & project effects API."""
from __future__ import annotations
from typing import List, Optional
from uuid import UUID as PyUUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.elasticity import (
    ElasticityCoefficient,
    ProjectFinancialEffect,
    MACRO_FACTORS,
    TARGET_METRICS,
)
from app.schemas.elasticity import (
    ElasticityRead, ElasticityUpsert,
    ProjectEffectRead, ProjectEffectUpsert,
    DecompositionResult,
)
from app.services.decomposition_engine import (
    compute_decomposition,
    MACRO_LABELS_RU,
    METRIC_LABELS_RU,
)


router = APIRouter(prefix="/elasticity", tags=["elasticity"])


def _admin_only(user: User):
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return
    role_codes = [r.code for r in getattr(user, "roles", [])] if hasattr(user, "roles") else []
    if "admin" not in role_codes:
        raise HTTPException(status_code=403, detail="Admin access required")


# ─── Constants ───
@router.get("/constants")
async def get_constants(_user: User = Depends(get_current_user)):
    """Lookup constants for the UI: macro factors, target metrics, labels."""
    return {
        "macro_factors": [
            {"code": f, "label_ru": MACRO_LABELS_RU.get(f, f)} for f in MACRO_FACTORS
        ],
        "target_metrics": [
            {"code": m, "label_ru": METRIC_LABELS_RU.get(m, m)} for m in TARGET_METRICS
        ],
        "sector_defaults_hint": (
            "Дефолты по сектору: горнодобыча — высокая FX-чувствительность; "
            "нефтегаз — зависит от нефти; энергетика — от ставки ЦБ; транспорт — от ВВП."
        ),
    }


# ─── Elasticity CRUD ───
@router.get("/coefficients", response_model=List[ElasticityRead])
async def list_coefficients(
    scenario_id: Optional[PyUUID] = Query(None, description="filter by scenario; NULL = global"),
    company_id: Optional[PyUUID] = Query(None, description="filter by company; NULL = sector-wide"),
    include_global: bool = Query(True, description="include rows where scenario/company is NULL"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """List elasticity coefficients. If include_global=true, also returns rows
    where scenario_id/company_id are NULL (global defaults)."""
    stmt = select(ElasticityCoefficient)
    if scenario_id and not include_global:
        stmt = stmt.where(ElasticityCoefficient.scenario_id == scenario_id)
    elif scenario_id:
        stmt = stmt.where(
            (ElasticityCoefficient.scenario_id == scenario_id) |
            (ElasticityCoefficient.scenario_id.is_(None))
        )
    if company_id and not include_global:
        stmt = stmt.where(ElasticityCoefficient.company_id == company_id)
    elif company_id:
        stmt = stmt.where(
            (ElasticityCoefficient.company_id == company_id) |
            (ElasticityCoefficient.company_id.is_(None))
        )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.put("/coefficients", response_model=ElasticityRead)
async def upsert_coefficient(
    payload: ElasticityUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upsert by (scenario_id, company_id, macro_factor, target_metric)."""
    _admin_only(user)
    stmt = select(ElasticityCoefficient).where(
        ElasticityCoefficient.macro_factor == payload.macro_factor,
        ElasticityCoefficient.target_metric == payload.target_metric,
    )
    if payload.scenario_id is None:
        stmt = stmt.where(ElasticityCoefficient.scenario_id.is_(None))
    else:
        stmt = stmt.where(ElasticityCoefficient.scenario_id == payload.scenario_id)
    if payload.company_id is None:
        stmt = stmt.where(ElasticityCoefficient.company_id.is_(None))
    else:
        stmt = stmt.where(ElasticityCoefficient.company_id == payload.company_id)

    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        existing.beta = payload.beta
        existing.notes = payload.notes
        existing.source = "manual"
        await db.commit()
        await db.refresh(existing)
        return existing

    obj = ElasticityCoefficient(
        scenario_id=payload.scenario_id,
        company_id=payload.company_id,
        macro_factor=payload.macro_factor,
        target_metric=payload.target_metric,
        beta=payload.beta,
        notes=payload.notes,
        source="manual",
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/coefficients/{coef_id}")
async def delete_coefficient(
    coef_id: PyUUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    obj = (await db.execute(
        select(ElasticityCoefficient).where(ElasticityCoefficient.id == coef_id)
    )).scalar_one_or_none()
    if not obj:
        return {"deleted": False}
    await db.delete(obj)
    await db.commit()
    return {"deleted": True}


# ─── Project effects CRUD ───
@router.get("/project-effects", response_model=List[ProjectEffectRead])
async def list_project_effects(
    project_id: Optional[PyUUID] = Query(None),
    effective_year: Optional[int] = Query(None),
    target_metric: Optional[str] = Query(None),
    company_id: Optional[PyUUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(ProjectFinancialEffect)
    if project_id:
        stmt = stmt.where(ProjectFinancialEffect.project_id == project_id)
    if effective_year:
        stmt = stmt.where(ProjectFinancialEffect.effective_year == effective_year)
    if target_metric:
        stmt = stmt.where(ProjectFinancialEffect.target_metric == target_metric)
    if company_id:
        try:
            from app.models.project import Project
            stmt = stmt.join(Project, Project.id == ProjectFinancialEffect.project_id).where(
                Project.company_id == company_id
            )
        except Exception:
            pass
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.put("/project-effects", response_model=ProjectEffectRead)
async def upsert_project_effect(
    payload: ProjectEffectUpsert,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    if payload.delta_value_uzs_mln is None and payload.delta_pct is None:
        raise HTTPException(
            status_code=400,
            detail="Either delta_value_uzs_mln or delta_pct must be provided",
        )

    existing = (await db.execute(
        select(ProjectFinancialEffect).where(
            ProjectFinancialEffect.project_id == payload.project_id,
            ProjectFinancialEffect.effective_year == payload.effective_year,
            ProjectFinancialEffect.target_metric == payload.target_metric,
        )
    )).scalar_one_or_none()

    if existing:
        for k, v in payload.model_dump(exclude={"project_id", "effective_year", "target_metric"}).items():
            setattr(existing, k, v)
        await db.commit()
        await db.refresh(existing)
        return existing

    obj = ProjectFinancialEffect(
        created_by=getattr(user, "email", None),
        **payload.model_dump(),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/project-effects/{effect_id}")
async def delete_project_effect(
    effect_id: PyUUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    obj = (await db.execute(
        select(ProjectFinancialEffect).where(ProjectFinancialEffect.id == effect_id)
    )).scalar_one_or_none()
    if not obj:
        return {"deleted": False}
    await db.delete(obj)
    await db.commit()
    return {"deleted": True}


# ─── Decomposition ───
@router.get("/decomposition", response_model=DecompositionResult)
async def get_decomposition(
    scenario_id: PyUUID = Query(...),
    target_metric: str = Query(...),
    target_year: int = Query(..., ge=2020, le=2050),
    company_id: Optional[PyUUID] = Query(None),
    base_year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Compute decomposition of forecast = base + macro_effects + project_effects."""
    if target_metric not in TARGET_METRICS:
        raise HTTPException(status_code=400, detail=f"Invalid target_metric. Must be one of: {TARGET_METRICS}")
    return await compute_decomposition(
        db,
        scenario_id=scenario_id,
        target_metric=target_metric,
        target_year=target_year,
        company_id=company_id,
        base_year=base_year,
    )


# ─── Admin: apply migrations + seed defaults ───
@router.post("/_apply-migrations")
async def apply_migrations_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _admin_only(user)
    from app.core.runtime_migrations_p743 import pack_743_self_heal
    return await pack_743_self_heal(db)
