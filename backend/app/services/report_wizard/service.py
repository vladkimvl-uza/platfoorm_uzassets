"""Report wizard config service — get / upsert по (company, year)."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_wizard import ReportWizardConfig
from app.models.user import User
from app.schemas.report_wizard import ReportWizardResponse


class ReportWizardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _row(self, company_id: UUID, year: int) -> Optional[ReportWizardConfig]:
        res = await self.db.execute(
            select(ReportWizardConfig).where(
                ReportWizardConfig.company_id == company_id,
                ReportWizardConfig.year == year,
            )
        )
        return res.scalar_one_or_none()

    async def get(self, company_id: UUID, year: int) -> ReportWizardResponse:
        row = await self._row(company_id, year)
        return ReportWizardResponse(
            config=(row.config if (row and row.config) else {}),
            updated_at=(row.updated_at if row else None),
            updated_by_name=(row.updated_by_name if row else None),
        )

    async def upsert(
        self, company_id: UUID, year: int, config: dict[str, Any], user: User,
    ) -> ReportWizardResponse:
        row = await self._row(company_id, year)
        name = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", None)
        )
        if row is None:
            row = ReportWizardConfig(
                company_id=company_id, year=year, config=config,
                updated_by=user.id, updated_by_name=name,
            )
            self.db.add(row)
        else:
            row.config = config
            row.updated_by = user.id
            row.updated_by_name = name
        await self.db.commit()
        await self.db.refresh(row)
        return ReportWizardResponse(
            config=row.config or {},
            updated_at=row.updated_at,
            updated_by_name=row.updated_by_name,
        )
