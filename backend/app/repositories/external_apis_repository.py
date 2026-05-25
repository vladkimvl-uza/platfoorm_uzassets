"""Data access for External APIs (3rd-party API registry)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_api import ExternalApi


class ExternalApisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, api_id: UUID) -> Optional[ExternalApi]:
        return await self.session.get(ExternalApi, api_id)

    async def get_by_slug(self, slug: str) -> Optional[ExternalApi]:
        res = await self.session.execute(
            select(ExternalApi).where(ExternalApi.slug == slug)
        )
        return res.scalars().first()

    async def list_apis(
        self,
        *,
        q: Optional[str],
        status_filter: Optional[str],
    ):
        base = select(ExternalApi)
        if q:
            like = f"%{q.lower()}%"
            base = base.where(or_(
                ExternalApi.slug.ilike(like),
                ExternalApi.name.ilike(like),
                ExternalApi.description.ilike(like),
            ))
        if status_filter:
            base = base.where(ExternalApi.status == status_filter)
        return list((await self.session.execute(
            base.order_by(ExternalApi.name)
        )).scalars().all())

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
