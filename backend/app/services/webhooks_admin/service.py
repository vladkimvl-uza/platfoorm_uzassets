"""Webhooks admin use-cases (Pack 12.1).

Service folder name: `webhooks_admin/` to avoid colliding with the core
`app.services.webhook_service` (delivery engine, untouched).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.webhooks_repository import WebhooksRepository
from app.schemas.webhook import (
    WebhookDeliveryListResponse,
    WebhookDeliveryRead,
    WebhookEventCatalogResponse,
    WebhookEventDef,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionListResponse,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
    WebhookTestRequest,
)
from app.services import webhook_service as core
from app.services.webhook_events import (
    EVENT_REGISTRY,
    get_grouped_events,
    is_registered,
)


def _validate_event_codes(codes) -> None:
    for ev in codes or []:
        if ev == "*" or ev.endswith(".*"):
            continue
        if not is_registered(ev):
            raise HTTPException(400, f"Unknown event code: {ev}")


@dataclass
class WebhooksService:
    async def list_events(self) -> WebhookEventCatalogResponse:
        events = [WebhookEventDef(**e) for e in EVENT_REGISTRY]
        grouped = {
            m: [WebhookEventDef(**e) for e in es]
            for m, es in get_grouped_events().items()
        }
        return WebhookEventCatalogResponse(
            events=events, grouped_by_module=grouped,
        )

    # ─── Subscriptions ───────────────────────────────────────────

    async def list_subscriptions(
        self, db: AsyncSession,
        *, service_account_id: Optional[UUID] = None,
    ) -> WebhookSubscriptionListResponse:
        rows = await WebhooksRepository(db).list_subscriptions(
            service_account_id=service_account_id,
        )
        return WebhookSubscriptionListResponse(
            items=[WebhookSubscriptionRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def create_subscription(
        self,
        body: WebhookSubscriptionCreate,
        db: AsyncSession,
        user: User,
    ) -> WebhookSubscriptionCreated:
        repo = WebhooksRepository(db)
        sa = await repo.get_service_account(body.service_account_id)
        if sa is None or not sa.is_service_account:
            raise HTTPException(404, "Service account not found")
        if not sa.is_active:
            raise HTTPException(400, "Service account is disabled")
        _validate_event_codes(body.events)

        sub, plaintext = await core.create_subscription(
            db,
            service_account_id=body.service_account_id,
            created_by_id=user.id,
            name=body.name,
            description=body.description,
            target_url=str(body.target_url),
            events=body.events or [],
            verify_ssl=body.verify_ssl,
            custom_headers=body.custom_headers,
            max_attempts=body.max_attempts,
            timeout_seconds=body.timeout_seconds,
        )
        out = WebhookSubscriptionCreated.model_validate(sub)
        out.plaintext_secret = plaintext
        return out

    async def get_subscription(
        self, sub_id: UUID, db: AsyncSession,
    ) -> WebhookSubscriptionRead:
        row = await WebhooksRepository(db).get_subscription(sub_id)
        if not row:
            raise HTTPException(404, "Subscription not found")
        return WebhookSubscriptionRead.model_validate(row)

    async def update_subscription(
        self, sub_id: UUID, body: WebhookSubscriptionUpdate,
        db: AsyncSession,
    ) -> WebhookSubscriptionRead:
        repo = WebhooksRepository(db)
        row = await repo.get_subscription(sub_id)
        if not row:
            raise HTTPException(404, "Subscription not found")
        data = body.model_dump(exclude_unset=True)
        if "events" in data and data["events"] is not None:
            _validate_event_codes(data["events"])
        for k, v in data.items():
            if k == "target_url" and v is not None:
                setattr(row, k, str(v))
            elif k == "is_active":
                if v is False and row.is_active:
                    row.disabled_at = datetime.now(UTC)
                    row.disabled_reason = "Manually disabled"
                elif v is True and not row.is_active:
                    row.disabled_at = None
                    row.disabled_reason = None
                    row.consecutive_failures = 0
                row.is_active = bool(v)
            else:
                setattr(row, k, v)
        row.updated_at = datetime.now(UTC)
        await db.commit()
        await repo.refresh(row)
        return WebhookSubscriptionRead.model_validate(row)

    async def delete_subscription(
        self, sub_id: UUID, db: AsyncSession,
    ) -> None:
        repo = WebhooksRepository(db)
        row = await repo.get_subscription(sub_id)
        if not row:
            raise HTTPException(404, "Subscription not found")
        await repo.delete(row)
        await db.commit()

    async def test_subscription(
        self,
        sub_id: UUID,
        body: WebhookTestRequest,
        db: AsyncSession,
        user: User,
    ) -> WebhookDeliveryRead:
        repo = WebhooksRepository(db)
        sub = await repo.get_subscription(sub_id)
        if not sub:
            raise HTTPException(404, "Subscription not found")
        if not sub.is_active:
            raise HTTPException(
                400, "Subscription is disabled; enable it before testing"
            )
        delivery = await core.enqueue_test(
            db, sub, body.payload, triggered_by_id=user.id,
        )
        return WebhookDeliveryRead.model_validate(delivery)

    # ─── Deliveries ──────────────────────────────────────────────

    async def list_deliveries(
        self,
        db: AsyncSession,
        *,
        subscription_id: Optional[UUID] = None,
        status_filter: Optional[str] = None,
        event_code: Optional[str] = None,
        limit: int = 100,
    ) -> WebhookDeliveryListResponse:
        rows = await WebhooksRepository(db).list_deliveries(
            subscription_id=subscription_id,
            status_filter=status_filter,
            event_code=event_code,
            limit=limit,
        )
        return WebhookDeliveryListResponse(
            items=[WebhookDeliveryRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def get_delivery(
        self, delivery_id: UUID, db: AsyncSession,
    ) -> WebhookDeliveryRead:
        row = await WebhooksRepository(db).get_delivery(delivery_id)
        if not row:
            raise HTTPException(404, "Delivery not found")
        return WebhookDeliveryRead.model_validate(row)

    async def replay_delivery(
        self, delivery_id: UUID, db: AsyncSession,
    ) -> WebhookDeliveryRead:
        original = await WebhooksRepository(db).get_delivery(delivery_id)
        if not original:
            raise HTTPException(404, "Delivery not found")
        try:
            new = await core.enqueue_replay(db, original)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return WebhookDeliveryRead.model_validate(new)

    # ─── Stats ───────────────────────────────────────────────────

    async def stats(self, db: AsyncSession) -> dict:
        return await WebhooksRepository(db).stats()
