"""Webhooks routes (Pack 12.1).

CRUD over subscriptions, event catalog, delivery log + replay/test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.models.user import User
from app.models.webhook import (
    WD_PENDING, WebhookDelivery, WebhookSubscription,
)
from app.schemas.webhook import (
    WebhookDeliveryListResponse, WebhookDeliveryReplayRequest, WebhookDeliveryRead,
    WebhookEventCatalogResponse, WebhookEventDef,
    WebhookSubscriptionCreate, WebhookSubscriptionCreated, WebhookSubscriptionListResponse,
    WebhookSubscriptionRead, WebhookSubscriptionUpdate, WebhookTestRequest,
)
from app.services import webhook_service as svc
from app.services.webhook_events import EVENT_REGISTRY, get_grouped_events, is_registered


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ════════════════════════════════════════════════════════════
#   Event catalog
# ════════════════════════════════════════════════════════════

@router.get("/events", response_model=WebhookEventCatalogResponse)
async def list_events(
    _u: User = Depends(require_permission("webhooks.read")),
):
    events = [WebhookEventDef(**e) for e in EVENT_REGISTRY]
    grouped = {m: [WebhookEventDef(**e) for e in es] for m, es in get_grouped_events().items()}
    return WebhookEventCatalogResponse(events=events, grouped_by_module=grouped)


# ════════════════════════════════════════════════════════════
#   Subscriptions CRUD
# ════════════════════════════════════════════════════════════

@router.get("/subscriptions", response_model=WebhookSubscriptionListResponse)
async def list_subscriptions(
    service_account_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    base = select(WebhookSubscription)
    if service_account_id is not None:
        base = base.where(WebhookSubscription.service_account_id == service_account_id)
    rows = (await db.execute(base.order_by(WebhookSubscription.created_at.desc()))).scalars().all()
    return WebhookSubscriptionListResponse(
        items=[WebhookSubscriptionRead.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post("/subscriptions", response_model=WebhookSubscriptionCreated, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: WebhookSubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("webhooks.manage")),
):
    # Validate SA exists and is a service account
    sa = await db.get(User, body.service_account_id)
    if sa is None or not sa.is_service_account:
        raise HTTPException(404, "Service account not found")
    if not sa.is_active:
        raise HTTPException(400, "Service account is disabled")

    # Validate events: each entry must be a literal registered code, "*", or "module.*"
    for ev in body.events or []:
        if ev == "*":
            continue
        if ev.endswith(".*"):
            continue  # wildcard, allowed
        if not is_registered(ev):
            raise HTTPException(400, f"Unknown event code: {ev}")

    sub, plaintext = await svc.create_subscription(
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


@router.get("/subscriptions/{sub_id}", response_model=WebhookSubscriptionRead)
async def get_subscription(
    sub_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    row = await db.get(WebhookSubscription, sub_id)
    if not row:
        raise HTTPException(404, "Subscription not found")
    return WebhookSubscriptionRead.model_validate(row)


@router.patch("/subscriptions/{sub_id}", response_model=WebhookSubscriptionRead)
async def update_subscription(
    sub_id: UUID,
    body: WebhookSubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.manage")),
):
    row = await db.get(WebhookSubscription, sub_id)
    if not row:
        raise HTTPException(404, "Subscription not found")

    data = body.model_dump(exclude_unset=True)
    if "events" in data and data["events"] is not None:
        for ev in data["events"]:
            if ev == "*" or ev.endswith(".*"):
                continue
            if not is_registered(ev):
                raise HTTPException(400, f"Unknown event code: {ev}")

    for k, v in data.items():
        if k == "target_url" and v is not None:
            setattr(row, k, str(v))
        elif k == "is_active":
            if v is False and row.is_active:
                row.disabled_at = datetime.now(timezone.utc)
                row.disabled_reason = "Manually disabled"
            elif v is True and not row.is_active:
                row.disabled_at = None
                row.disabled_reason = None
                row.consecutive_failures = 0
            row.is_active = bool(v)
        else:
            setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return WebhookSubscriptionRead.model_validate(row)


@router.delete("/subscriptions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    sub_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.manage")),
):
    row = await db.get(WebhookSubscription, sub_id)
    if not row:
        raise HTTPException(404, "Subscription not found")
    await db.delete(row)
    await db.commit()


@router.post("/subscriptions/{sub_id}/test", response_model=WebhookDeliveryRead)
async def test_subscription(
    sub_id: UUID,
    body: WebhookTestRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("webhooks.manage")),
):
    sub = await db.get(WebhookSubscription, sub_id)
    if not sub:
        raise HTTPException(404, "Subscription not found")
    if not sub.is_active:
        raise HTTPException(400, "Subscription is disabled; enable it before testing")

    delivery = await svc.enqueue_test(db, sub, body.payload, triggered_by_id=user.id)
    return WebhookDeliveryRead.model_validate(delivery)


# ════════════════════════════════════════════════════════════
#   Deliveries log
# ════════════════════════════════════════════════════════════

@router.get("/deliveries", response_model=WebhookDeliveryListResponse)
async def list_deliveries(
    subscription_id: Optional[UUID] = Query(None),
    status_filter:   Optional[str]  = Query(None, alias="status"),
    event_code:      Optional[str]  = Query(None),
    limit:           int            = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    q = select(WebhookDelivery)
    if subscription_id is not None: q = q.where(WebhookDelivery.subscription_id == subscription_id)
    if status_filter   is not None: q = q.where(WebhookDelivery.status == status_filter)
    if event_code      is not None: q = q.where(WebhookDelivery.event_code == event_code)
    rows = (await db.execute(q.order_by(WebhookDelivery.created_at.desc()).limit(limit))).scalars().all()
    return WebhookDeliveryListResponse(
        items=[WebhookDeliveryRead.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get("/deliveries/{delivery_id}", response_model=WebhookDeliveryRead)
async def get_delivery(
    delivery_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    row = await db.get(WebhookDelivery, delivery_id)
    if not row:
        raise HTTPException(404, "Delivery not found")
    return WebhookDeliveryRead.model_validate(row)


@router.post("/deliveries/{delivery_id}/replay", response_model=WebhookDeliveryRead)
async def replay_delivery(
    delivery_id: UUID,
    body: WebhookDeliveryReplayRequest,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.manage")),
):
    original = await db.get(WebhookDelivery, delivery_id)
    if not original:
        raise HTTPException(404, "Delivery not found")
    try:
        new = await svc.enqueue_replay(db, original)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return WebhookDeliveryRead.model_validate(new)


# ════════════════════════════════════════════════════════════
#   Stats
# ════════════════════════════════════════════════════════════

@router.get("/stats")
async def stats(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("webhooks.read")),
):
    total_subs   = int((await db.execute(select(func.count(WebhookSubscription.id)))).scalar_one() or 0)
    active_subs  = int((await db.execute(
        select(func.count(WebhookSubscription.id)).where(WebhookSubscription.is_active.is_(True)),
    )).scalar_one() or 0)
    pending      = int((await db.execute(
        select(func.count(WebhookDelivery.id)).where(WebhookDelivery.status == WD_PENDING),
    )).scalar_one() or 0)

    # Last 24h success rate
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    total_24h    = int((await db.execute(
        select(func.count(WebhookDelivery.id)).where(WebhookDelivery.created_at >= cutoff),
    )).scalar_one() or 0)
    success_24h  = int((await db.execute(
        select(func.count(WebhookDelivery.id)).where(and_(
            WebhookDelivery.created_at >= cutoff,
            WebhookDelivery.status == "succeeded",
        )),
    )).scalar_one() or 0)

    return {
        "subscriptions": {"total": total_subs, "active": active_subs},
        "pending_deliveries": pending,
        "last_24h": {
            "total": total_24h,
            "succeeded": success_24h,
            "success_rate": round(success_24h / total_24h, 4) if total_24h else None,
        },
    }
