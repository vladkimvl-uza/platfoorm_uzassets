"""Data access for Integration Partners domain."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.external_api import ExternalApi
from app.models.partner import IntegrationPartner
from app.models.user import User
from app.models.webhook import WebhookSubscription


class PartnersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── single lookups ───────────────────────────────────────────

    async def get(self, partner_id: UUID) -> Optional[IntegrationPartner]:
        return await self.session.get(IntegrationPartner, partner_id)

    async def get_by_slug(self, slug: str) -> Optional[IntegrationPartner]:
        res = await self.session.execute(
            select(IntegrationPartner).where(IntegrationPartner.slug == slug)
        )
        return res.scalars().first()

    async def get_service_account(self, user_id: UUID) -> Optional[User]:
        return await self.session.get(User, user_id)

    async def get_external_api(self, api_id: UUID) -> Optional[ExternalApi]:
        return await self.session.get(ExternalApi, api_id)

    async def get_webhook(self, hook_id: UUID) -> Optional[WebhookSubscription]:
        return await self.session.get(WebhookSubscription, hook_id)

    # ─── listings ─────────────────────────────────────────────────

    async def list_partners(
        self,
        *,
        q: Optional[str],
        status_filter: Optional[str],
    ):
        base = select(IntegrationPartner)
        if q:
            like = f"%{q.lower()}%"
            base = base.where(or_(
                IntegrationPartner.slug.ilike(like),
                IntegrationPartner.name.ilike(like),
                IntegrationPartner.legal_name.ilike(like),
            ))
        if status_filter:
            base = base.where(IntegrationPartner.status == status_filter)
        return list((await self.session.execute(
            base.order_by(IntegrationPartner.name)
        )).scalars().all())

    async def list_partner_service_accounts(self, partner_id: UUID):
        res = await self.session.execute(
            select(User).where(and_(
                User.partner_id == partner_id,
                User.is_service_account.is_(True),
            ))
        )
        return list(res.scalars().all())

    async def list_partner_external_apis(self, partner_id: UUID):
        res = await self.session.execute(
            select(ExternalApi).where(ExternalApi.partner_id == partner_id)
        )
        return list(res.scalars().all())

    async def list_partner_webhooks(self, partner_id: UUID):
        res = await self.session.execute(
            select(WebhookSubscription).where(WebhookSubscription.partner_id == partner_id)
        )
        return list(res.scalars().all())

    # ─── counts ───────────────────────────────────────────────────

    async def count_service_accounts(self, partner_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(User.id)).where(and_(
                User.partner_id == partner_id,
                User.is_service_account.is_(True),
            ))
        )
        return int(res.scalar_one() or 0)

    async def count_api_keys(self, partner_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(ApiKey.id))
            .join(User, ApiKey.service_account_id == User.id)
            .where(User.partner_id == partner_id)
        )
        return int(res.scalar_one() or 0)

    async def count_webhooks(self, partner_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(WebhookSubscription.id))
            .where(WebhookSubscription.partner_id == partner_id)
        )
        return int(res.scalar_one() or 0)

    async def count_external_apis(self, partner_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(ExternalApi.id))
            .where(ExternalApi.partner_id == partner_id)
        )
        return int(res.scalar_one() or 0)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
