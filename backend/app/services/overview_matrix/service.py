"""Overview matrix config service — get / upsert по (company, year)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.overview_matrix import OverviewMatrixConfig
from app.models.user import User
from app.schemas.overview_matrix import MatrixConfig, MatrixConfigResponse


class OverviewMatrixService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_row(self, company_id: UUID, year: int) -> Optional[OverviewMatrixConfig]:
        res = await self.db.execute(
            select(OverviewMatrixConfig).where(
                OverviewMatrixConfig.company_id == company_id,
                OverviewMatrixConfig.year == year,
            )
        )
        return res.scalar_one_or_none()

    async def get(self, company_id: UUID, year: int) -> MatrixConfigResponse:
        row = await self._get_row(company_id, year)
        cfg = MatrixConfig.model_validate(row.config) if (row and row.config) else MatrixConfig()
        return MatrixConfigResponse(
            company_id=company_id,
            year=year,
            config=cfg,
            updated_at=(row.updated_at if row else None),
            updated_by_name=(row.updated_by_name if row else None),
        )

    async def upsert(
        self, company_id: UUID, year: int, config: MatrixConfig, user: User,
    ) -> MatrixConfigResponse:
        row = await self._get_row(company_id, year)
        payload = config.model_dump(mode="json")
        name = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
        )
        if row is None:
            row = OverviewMatrixConfig(
                company_id=company_id, year=year, config=payload,
                updated_by=user.id, updated_by_name=name,
            )
            self.db.add(row)
        else:
            row.config = payload
            row.updated_by = user.id
            row.updated_by_name = name
        await self.db.commit()
        await self.db.refresh(row)
        return MatrixConfigResponse(
            company_id=company_id,
            year=year,
            config=MatrixConfig.model_validate(row.config),
            updated_at=row.updated_at,
            updated_by_name=row.updated_by_name,
        )
