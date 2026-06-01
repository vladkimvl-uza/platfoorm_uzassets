"""Persistence layer for Webhooks (Pack 12.1)."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.webhook import (
    WD_PENDING,
    WebhookDelivery,
    WebhookSubscription,
)


class WebhooksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete(self, obj: Any) -> None:
        await self._session.delete(obj)

    async def refresh(self, obj: Any) -> None:
        await self._session.refresh(obj)

    # ─── Subscriptions ───────────────────────────────────────────

    async def list_subscriptions(
        self, *, service_account_id: Optional[UUID] = None
    ) -> Sequence[WebhookSubscription]:
        base = select(WebhookSubscription)
        if service_account_id is not None:
            base = base.where(
                WebhookSubscription.service_account_id == service_account_id
            )
        return (await self._session.execute(
            base.order_by(WebhookSubscription.created_at.desc())
        )).scalars().all()

    async def get_subscription(self, sub_id: UUID) -> Optional[WebhookSubscription]:
        return await self._session.get(WebhookSubscription, sub_id)

    async def get_service_account(self, sa_id: UUID) -> Optional[User]:
        return await self._session.get(User, sa_id)

    # ─── Deliveries ──────────────────────────────────────────────

    async def list_deliveries(
        self,
        *,
        subscription_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        event_code: Optional[str] = None,
        limit: int = 100,
    ) -> Sequence[WebhookDelivery]:
        q = select(WebhookDelivery)
        if subscription_id is not None:
            q = q.where(WebhookDelivery.subscription_id == subscription_id)
        if status_filter is not None:
            q = q.where(WebhookDelivery.status == status_filter)
        if event_code is not None:
            q = q.where(WebhookDelivery.event_code == event_code)
        return (await self._session.execute(
            q.order_by(WebhookDelivery.created_at.desc()).limit(limit)
        )).scalars().all()

    async def get_delivery(self, delivery_id: UUID) -> Optional[WebhookDelivery]:
        return await self._session.get(WebhookDelivery, delivery_id)

    # ─── Stats ───────────────────────────────────────────────────

    async def stats(self) -> dict:
        total_subs = int((await self._session.execute(
            select(func.count(WebhookSubscription.id))
        )).scalar_one() or 0)
        active_subs = int((await self._session.execute(
            select(func.count(WebhookSubscription.id))
            .where(WebhookSubscription.is_active.is_(True))
        )).scalar_one() or 0)
        pending = int((await self._session.execute(
            select(func.count(WebhookDelivery.id))
            .where(WebhookDelivery.status == WD_PENDING)
        )).scalar_one() or 0)

        cutoff = datetime.now(UTC) - timedelta(hours=24)
        total_24h = int((await self._session.execute(
            select(func.count(WebhookDelivery.id))
            .where(WebhookDelivery.created_at >= cutoff)
        )).scalar_one() or 0)
        success_24h = int((await self._session.execute(
            select(func.count(WebhookDelivery.id)).where(and_(
                WebhookDelivery.created_at >= cutoff,
                WebhookDelivery.status == "succeeded",
            ))
        )).scalar_one() or 0)

        return {
            "subscriptions": {"total": total_subs, "active": active_subs},
            "pending_deliveries": pending,
            "last_24h": {
                "total": total_24h,
                "succeeded": success_24h,
                "success_rate": (
                    round(success_24h / total_24h, 4) if total_24h else None
                ),
            },
        }
