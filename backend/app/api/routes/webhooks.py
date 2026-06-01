"""Webhooks routes (Pack 12.1) — thin HTTP shim (refactored 2026-05-25).

CRUD over subscriptions, event catalog, delivery log + replay/test.
Core delivery engine lives in `app.services.webhook_service` (untouched).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.dependencies.webhooks import WebhooksServiceDep
from app.models.user import User
from app.schemas.webhook import (
    WebhookDeliveryListResponse,
    WebhookDeliveryRead,
    WebhookDeliveryReplayRequest,
    WebhookEventCatalogResponse,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionListResponse,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
    WebhookTestRequest,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ─── Event catalog ────────────────────────────────────────────────

@router.get("/events", response_model=WebhookEventCatalogResponse)
async def list_events(
    service: WebhooksServiceDep,
    _u: User = Depends(require_permission("webhooks.read")),
):
    return await service.list_events()


# ─── Subscriptions CRUD ───────────────────────────────────────────

@router.get("/subscriptions", response_model=WebhookSubscriptionListResponse)
async def list_subscriptions(
    service: WebhooksServiceDep,
    service_account_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    return await service.list_subscriptions(
        db, service_account_id=service_account_id,
    )


@router.post(
    "/subscriptions",
    response_model=WebhookSubscriptionCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    body: WebhookSubscriptionCreate,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("webhooks.manage")),
):
    return await service.create_subscription(body, db, user)


@router.get("/subscriptions/{sub_id}", response_model=WebhookSubscriptionRead)
async def get_subscription(
    sub_id: UUID,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    return await service.get_subscription(sub_id, db)


@router.patch("/subscriptions/{sub_id}", response_model=WebhookSubscriptionRead)
async def update_subscription(
    sub_id: UUID,
    body: WebhookSubscriptionUpdate,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.manage")),
):
    return await service.update_subscription(sub_id, body, db)


@router.delete(
    "/subscriptions/{sub_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_subscription(
    sub_id: UUID,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.manage")),
):
    await service.delete_subscription(sub_id, db)


@router.post("/subscriptions/{sub_id}/test", response_model=WebhookDeliveryRead)
async def test_subscription(
    sub_id: UUID,
    body: WebhookTestRequest,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("webhooks.manage")),
):
    return await service.test_subscription(sub_id, body, db, user)


# ─── Deliveries log ───────────────────────────────────────────────

@router.get("/deliveries", response_model=WebhookDeliveryListResponse)
async def list_deliveries(
    service: WebhooksServiceDep,
    subscription_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    event_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    return await service.list_deliveries(
        db,
        subscription_id=subscription_id,
        status_filter=status_filter,
        event_code=event_code,
        limit=limit,
    )


@router.get("/deliveries/{delivery_id}", response_model=WebhookDeliveryRead)
async def get_delivery(
    delivery_id: UUID,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    return await service.get_delivery(delivery_id, db)


@router.post(
    "/deliveries/{delivery_id}/replay", response_model=WebhookDeliveryRead,
)
async def replay_delivery(
    delivery_id: UUID,
    body: WebhookDeliveryReplayRequest,
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.manage")),
):
    return await service.replay_delivery(delivery_id, db)


# ─── Stats ────────────────────────────────────────────────────────

@router.get("/stats")
async def stats(
    service: WebhooksServiceDep,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    return await service.stats(db)
