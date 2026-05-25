"""Admin broadcast REST routes — thin HTTP layer (refactored 2026-05-25).

All admin_router endpoints under /admin-broadcasts (perm: notifications.broadcast).
user_router endpoints under /broadcasts (any authenticated user).

Core dispatch engine in `app/services/admin_broadcast_service.py` not touched.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.security import get_current_user, require_permission
from app.dependencies.admin_broadcasts import AdminBroadcastsServiceDep
from app.models.admin_broadcast import (
    ACK_MODES, BROADCAST_PRIORITIES, BROADCAST_TYPES, SCHEDULE_MODES,
)
from app.models.user import User
from app.schemas.admin_broadcast import (
    AckRead, AckSubmit, BroadcastAnalytics,
    DispatchListResponse, DispatchRead,
    RecipientPreview, StickyNotification,
    TemplateCreate, TemplateListResponse,
    TemplateRead, TemplateUpdate,
)


admin_router = APIRouter(prefix="/admin-broadcasts", tags=["admin-broadcasts"])
user_router  = APIRouter(prefix="/broadcasts",       tags=["broadcasts"])

# Auto-loader picks up `router`; user_router is mounted separately in main.py.
router = admin_router


# ─── Catalog ─────────────────────────────────────────────────────

@admin_router.get("/catalog")
async def catalog(_u: User = Depends(require_permission("notifications.broadcast"))):
    return {
        "types":      BROADCAST_TYPES,
        "priorities": BROADCAST_PRIORITIES,
        "ack_modes":  ACK_MODES,
        "schedule_modes": SCHEDULE_MODES,
    }


# ─── Template CRUD ───────────────────────────────────────────────

@admin_router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    service: AdminBroadcastsServiceDep,
    is_active: Optional[bool] = Query(None),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.list_templates(is_active=is_active)


@admin_router.get("/templates/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.get_template(template_id)


@admin_router.post("/templates", response_model=TemplateRead,
                   status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    service: AdminBroadcastsServiceDep,
    user: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.create_template(body, created_by_id=user.id)


@admin_router.patch("/templates/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    body: TemplateUpdate,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.update_template(template_id, body)


@admin_router.delete("/templates/{template_id}",
                     status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    await service.delete_template(template_id)


@admin_router.post("/templates/{template_id}/toggle", response_model=TemplateRead)
async def toggle_template(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.toggle_template(template_id)


# ─── Preview / Send-now / Test-on-self ───────────────────────────

@admin_router.get("/templates/{template_id}/preview-recipients",
                  response_model=RecipientPreview)
async def preview(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.preview_recipients(template_id)


@admin_router.post("/templates/{template_id}/send-now", response_model=DispatchRead)
async def send_now(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    user: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.send_now(template_id, triggered_by_id=user.id)


@admin_router.post("/templates/{template_id}/test-on-self",
                   response_model=DispatchRead)
async def test_on_self(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    user: User = Depends(require_permission("notifications.broadcast")),
):
    """Send to the caller only (override targeting), for QA."""
    return await service.test_on_self(template_id, user_id=user.id)


# ─── Dispatch history + analytics ────────────────────────────────

@admin_router.get("/templates/{template_id}/dispatches",
                  response_model=DispatchListResponse)
async def list_dispatches(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.list_dispatches(template_id)


@admin_router.get("/templates/{template_id}/analytics",
                  response_model=BroadcastAnalytics)
async def analytics(
    template_id: UUID,
    service: AdminBroadcastsServiceDep,
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    return await service.analytics(template_id)


# ─── Recipient-facing endpoints (any authenticated user) ─────────

@user_router.get("/sticky", response_model=list[StickyNotification])
async def my_sticky(
    service: AdminBroadcastsServiceDep,
    user: User = Depends(get_current_user),
):
    """Return all pending sticky notifications for the current user.

    Frontend mounts a global modal that subscribes to this; loops while
    `acknowledged_at IS NULL`.
    """
    return await service.my_sticky(user.id)


@user_router.post("/{notification_id}/ack", response_model=AckRead)
async def ack(
    notification_id: UUID,
    body: AckSubmit,
    service: AdminBroadcastsServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.acknowledge(notification_id, body, user=user)
