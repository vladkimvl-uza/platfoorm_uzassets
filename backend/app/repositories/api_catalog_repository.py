"""Data access for API Catalog — permissions list + company lookup."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.user import Permission


class ApiCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_permissions(self):
        res = await self.session.execute(
            select(Permission).order_by(Permission.module, Permission.code)
        )
        return list(res.scalars().all())

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        return await self.session.get(Company, company_id)
