"""Persistence layer for elasticity coefficients + project financial effects."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.elasticity import ElasticityCoefficient, ProjectFinancialEffect


class ElasticityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, obj: Any) -> None:
        self._session.add(obj)

    async def delete(self, obj: Any) -> None:
        await self._session.delete(obj)

    async def refresh(self, obj: Any) -> None:
        await self._session.refresh(obj)

    # ─── Coefficients ────────────────────────────────────────────

    async def list_coefficients(
        self,
        *,
        scenario_id: Optional[UUID],
        company_id: Optional[UUID],
        include_global: bool,
    ) -> Sequence[ElasticityCoefficient]:
        stmt = select(ElasticityCoefficient)
        if scenario_id and not include_global:
            stmt = stmt.where(ElasticityCoefficient.scenario_id == scenario_id)
        elif scenario_id:
            stmt = stmt.where(
                (ElasticityCoefficient.scenario_id == scenario_id)
                | (ElasticityCoefficient.scenario_id.is_(None))
            )
        if company_id and not include_global:
            stmt = stmt.where(ElasticityCoefficient.company_id == company_id)
        elif company_id:
            stmt = stmt.where(
                (ElasticityCoefficient.company_id == company_id)
                | (ElasticityCoefficient.company_id.is_(None))
            )
        return (await self._session.execute(stmt)).scalars().all()

    async def find_coefficient(
        self,
        *,
        scenario_id: Optional[UUID],
        company_id: Optional[UUID],
        macro_factor: str,
        target_metric: str,
    ) -> Optional[ElasticityCoefficient]:
        stmt = select(ElasticityCoefficient).where(
            ElasticityCoefficient.macro_factor == macro_factor,
            ElasticityCoefficient.target_metric == target_metric,
        )
        if scenario_id is None:
            stmt = stmt.where(ElasticityCoefficient.scenario_id.is_(None))
        else:
            stmt = stmt.where(ElasticityCoefficient.scenario_id == scenario_id)
        if company_id is None:
            stmt = stmt.where(ElasticityCoefficient.company_id.is_(None))
        else:
            stmt = stmt.where(ElasticityCoefficient.company_id == company_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_coefficient(
        self, coef_id: UUID
    ) -> Optional[ElasticityCoefficient]:
        return (await self._session.execute(
            select(ElasticityCoefficient).where(
                ElasticityCoefficient.id == coef_id
            )
        )).scalar_one_or_none()

    # ─── Project effects ─────────────────────────────────────────

    async def list_project_effects(
        self,
        *,
        project_id: Optional[UUID] = None,
        effective_year: Optional[int] = None,
        target_metric: Optional[str] = None,
        company_id: Optional[UUID] = None,
    ) -> Sequence[ProjectFinancialEffect]:
        stmt = select(ProjectFinancialEffect)
        if project_id:
            stmt = stmt.where(ProjectFinancialEffect.project_id == project_id)
        if effective_year:
            stmt = stmt.where(
                ProjectFinancialEffect.effective_year == effective_year
            )
        if target_metric:
            stmt = stmt.where(
                ProjectFinancialEffect.target_metric == target_metric
            )
        if company_id:
            try:
                from app.models.project import Project
                stmt = stmt.join(
                    Project, Project.id == ProjectFinancialEffect.project_id
                ).where(Project.company_id == company_id)
            except Exception:
                pass
        return (await self._session.execute(stmt)).scalars().all()

    async def find_project_effect(
        self,
        *,
        project_id: UUID,
        effective_year: int,
        target_metric: str,
    ) -> Optional[ProjectFinancialEffect]:
        return (await self._session.execute(
            select(ProjectFinancialEffect).where(
                ProjectFinancialEffect.project_id == project_id,
                ProjectFinancialEffect.effective_year == effective_year,
                ProjectFinancialEffect.target_metric == target_metric,
            )
        )).scalar_one_or_none()

    async def get_project_effect(
        self, effect_id: UUID
    ) -> Optional[ProjectFinancialEffect]:
        return (await self._session.execute(
            select(ProjectFinancialEffect).where(
                ProjectFinancialEffect.id == effect_id
            )
        )).scalar_one_or_none()
