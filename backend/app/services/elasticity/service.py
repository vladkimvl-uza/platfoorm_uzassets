"""Elasticity & project effects use-cases (Pack 7.43).

Admin-only mutations. Decomposition delegates to the existing
`compute_decomposition` helper unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.elasticity import (
    ElasticityCoefficient, MACRO_FACTORS, ProjectFinancialEffect,
    TARGET_METRICS,
)
from app.models.user import User
from app.repositories.elasticity_repository import ElasticityRepository
from app.schemas.elasticity import (
    DecompositionResult, ElasticityRead, ElasticityUpsert,
    ProjectEffectRead, ProjectEffectUpsert,
)
from app.services.decomposition_engine import (
    compute_decomposition, MACRO_LABELS_RU, METRIC_LABELS_RU,
)


def _admin_only(user: User) -> None:
    if getattr(user, "email", "") == "v.kim@uz-assets.uz":
        return
    role_codes = (
        [r.code for r in getattr(user, "roles", [])]
        if hasattr(user, "roles") else []
    )
    if "admin" not in role_codes:
        raise HTTPException(status_code=403, detail="Admin access required")


@dataclass
class ElasticityService:
    async def constants(self) -> dict:
        return {
            "macro_factors": [
                {"code": f, "label_ru": MACRO_LABELS_RU.get(f, f)}
                for f in MACRO_FACTORS
            ],
            "target_metrics": [
                {"code": m, "label_ru": METRIC_LABELS_RU.get(m, m)}
                for m in TARGET_METRICS
            ],
            "sector_defaults_hint": (
                "Дефолты по сектору: горнодобыча — высокая FX-чувствительность; "
                "нефтегаз — зависит от нефти; энергетика — от ставки ЦБ; "
                "транспорт — от ВВП."
            ),
        }

    # ─── Coefficients ────────────────────────────────────────────

    async def list_coefficients(
        self,
        db: AsyncSession,
        *,
        scenario_id: Optional[UUID],
        company_id: Optional[UUID],
        include_global: bool,
    ) -> List[ElasticityCoefficient]:
        return list(await ElasticityRepository(db).list_coefficients(
            scenario_id=scenario_id, company_id=company_id,
            include_global=include_global,
        ))

    async def upsert_coefficient(
        self, payload: ElasticityUpsert, db: AsyncSession, user: User,
    ) -> ElasticityCoefficient:
        _admin_only(user)
        repo = ElasticityRepository(db)
        existing = await repo.find_coefficient(
            scenario_id=payload.scenario_id,
            company_id=payload.company_id,
            macro_factor=payload.macro_factor,
            target_metric=payload.target_metric,
        )
        if existing:
            existing.beta = payload.beta
            existing.notes = payload.notes
            existing.source = "manual"
            await db.commit()
            await repo.refresh(existing)
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
        repo.add(obj)
        await db.commit()
        await repo.refresh(obj)
        return obj

    async def delete_coefficient(
        self, coef_id: UUID, db: AsyncSession, user: User,
    ) -> dict:
        _admin_only(user)
        repo = ElasticityRepository(db)
        obj = await repo.get_coefficient(coef_id)
        if not obj:
            return {"deleted": False}
        await repo.delete(obj)
        await db.commit()
        return {"deleted": True}

    # ─── Project effects ─────────────────────────────────────────

    async def list_project_effects(
        self,
        db: AsyncSession,
        *,
        project_id: Optional[UUID] = None,
        effective_year: Optional[int] = None,
        target_metric: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> List[ProjectFinancialEffect]:
        return list(await ElasticityRepository(db).list_project_effects(
            project_id=project_id, effective_year=effective_year,
            target_metric=target_metric, company_id=company_id,
        ))

    async def upsert_project_effect(
        self, payload: ProjectEffectUpsert, db: AsyncSession, user: User,
    ) -> ProjectFinancialEffect:
        _admin_only(user)
        if payload.delta_value_uzs_mln is None and payload.delta_pct is None:
            raise HTTPException(
                status_code=400,
                detail="Either delta_value_uzs_mln or delta_pct must be provided",
            )
        repo = ElasticityRepository(db)
        existing = await repo.find_project_effect(
            project_id=payload.project_id,
            effective_year=payload.effective_year,
            target_metric=payload.target_metric,
        )
        if existing:
            for k, v in payload.model_dump(
                exclude={"project_id", "effective_year", "target_metric"}
            ).items():
                setattr(existing, k, v)
            await db.commit()
            await repo.refresh(existing)
            return existing
        obj = ProjectFinancialEffect(
            created_by=getattr(user, "email", None),
            **payload.model_dump(),
        )
        repo.add(obj)
        await db.commit()
        await repo.refresh(obj)
        return obj

    async def delete_project_effect(
        self, effect_id: UUID, db: AsyncSession, user: User,
    ) -> dict:
        _admin_only(user)
        repo = ElasticityRepository(db)
        obj = await repo.get_project_effect(effect_id)
        if not obj:
            return {"deleted": False}
        await repo.delete(obj)
        await db.commit()
        return {"deleted": True}

    # ─── Decomposition + migrations ──────────────────────────────

    async def decomposition(
        self,
        db: AsyncSession,
        *,
        scenario_id: UUID,
        target_metric: str,
        target_year: int,
        company_id: Optional[UUID] = None,
        base_year: Optional[int] = None,
    ) -> DecompositionResult:
        if target_metric not in TARGET_METRICS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target_metric. Must be one of: {TARGET_METRICS}",
            )
        return await compute_decomposition(
            db,
            scenario_id=scenario_id, target_metric=target_metric,
            target_year=target_year, company_id=company_id,
            base_year=base_year,
        )

    async def apply_migrations(self, db: AsyncSession, user: User):
        _admin_only(user)
        from app.core.runtime_migrations_p743 import pack_743_self_heal
        return await pack_743_self_heal(db)
