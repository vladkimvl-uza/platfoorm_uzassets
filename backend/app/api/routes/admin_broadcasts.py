"""Admin broadcast REST routes (Pack 11.2).

All under /admin-broadcasts/* (admin only) + /broadcasts/* for recipient actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.admin_broadcast import (
    ACK_MODES, BROADCAST_PRIORITIES, BROADCAST_TYPES, SCHEDULE_MODES,
    AdminBroadcastAck, AdminBroadcastDispatch, AdminBroadcastTemplate,
)
from app.models.notification import Notification
from app.models.user import User
from app.schemas.admin_broadcast import (
    AckRead, AckSubmit, BroadcastAnalytics,
    DispatchListResponse, DispatchRead,
    RecipientPreview, StickyNotification,
    TemplateCreate, TemplateListItem, TemplateListResponse,
    TemplateRead, TemplateUpdate,
)
from app.services import admin_broadcast_service as svc


admin_router = APIRouter(prefix="/admin-broadcasts", tags=["admin-broadcasts"])
user_router  = APIRouter(prefix="/broadcasts",       tags=["broadcasts"])

# Auto-loader picks up `router`; user_router is mounted separately in main.py.
router = admin_router


# ════════════════════════════════════════════════════════════
#   Catalog
# ════════════════════════════════════════════════════════════

@admin_router.get("/catalog")
async def catalog(_u: User = Depends(require_permission("notifications.broadcast"))):
    return {
        "types":      BROADCAST_TYPES,
        "priorities": BROADCAST_PRIORITIES,
        "ack_modes":  ACK_MODES,
        "schedule_modes": SCHEDULE_MODES,
    }


# ════════════════════════════════════════════════════════════
#   Template CRUD
# ════════════════════════════════════════════════════════════

@admin_router.get("/templates", response_model=TemplateListResponse)
async def list_templates(
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    base = select(AdminBroadcastTemplate)
    if is_active is not None:
        base = base.where(AdminBroadcastTemplate.is_active.is_(is_active))
    rows = (await db.execute(base.order_by(AdminBroadcastTemplate.created_at.desc()))).scalars().all()
    return TemplateListResponse(
        items=[TemplateListItem.model_validate(r) for r in rows],
        total=len(rows),
    )


@admin_router.get("/templates/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")
    return TemplateRead.model_validate(t)


@admin_router.post("/templates", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications.broadcast")),
):
    now = datetime.now(timezone.utc)
    data = body.model_dump(exclude_unset=True)
    if data.get("schedule_config"):
        data["schedule_config"] = data["schedule_config"] if isinstance(data["schedule_config"], dict) \
                                  else data["schedule_config"].model_dump()
    if data.get("target_filter_expr"):
        data["target_filter_expr"] = data["target_filter_expr"] if isinstance(data["target_filter_expr"], dict) \
                                     else data["target_filter_expr"].model_dump()

    t = AdminBroadcastTemplate(created_at=now, updated_at=now, created_by_id=user.id, **data)
    t.next_run_at = svc.compute_next_run_at(t, after=now)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return TemplateRead.model_validate(t)


@admin_router.patch("/templates/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: UUID,
    body: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")

    data = body.model_dump(exclude_unset=True)
    if data.get("schedule_config"):
        data["schedule_config"] = data["schedule_config"] if isinstance(data["schedule_config"], dict) \
                                  else data["schedule_config"].model_dump()
    if data.get("target_filter_expr"):
        data["target_filter_expr"] = data["target_filter_expr"] if isinstance(data["target_filter_expr"], dict) \
                                     else data["target_filter_expr"].model_dump()
    for k, v in data.items():
        setattr(t, k, v)
    t.updated_at = datetime.now(timezone.utc)
    t.next_run_at = svc.compute_next_run_at(t, after=t.updated_at)
    await db.commit()
    await db.refresh(t)
    return TemplateRead.model_validate(t)


@admin_router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")
    await db.delete(t)
    await db.commit()


@admin_router.post("/templates/{template_id}/toggle", response_model=TemplateRead)
async def toggle_template(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")
    t.is_active = not t.is_active
    t.updated_at = datetime.now(timezone.utc)
    if t.is_active:
        t.next_run_at = svc.compute_next_run_at(t, after=t.updated_at)
    else:
        t.next_run_at = None
    await db.commit()
    await db.refresh(t)
    return TemplateRead.model_validate(t)


# ════════════════════════════════════════════════════════════
#   Preview / Send-now / Test-on-self
# ════════════════════════════════════════════════════════════

@admin_router.get("/templates/{template_id}/preview-recipients", response_model=RecipientPreview)
async def preview(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")
    res = await svc.preview_recipients(db, t)
    return RecipientPreview(**res)


@admin_router.post("/templates/{template_id}/send-now", response_model=DispatchRead)
async def send_now(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")
    d = await svc.dispatch_template(db, template=t, triggered_by_id=user.id, trigger="manual")
    return DispatchRead.model_validate(d)


@admin_router.post("/templates/{template_id}/test-on-self", response_model=DispatchRead)
async def test_on_self(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("notifications.broadcast")),
):
    """Send to the caller only (override targeting), for QA."""
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")

    # Temporarily clone-and-override targeting
    original_all = t.target_all
    original_users = t.target_user_ids
    original_groups = t.target_group_codes
    original_roles  = t.target_role_codes
    original_filter = t.target_filter_expr
    t.target_all = False
    t.target_user_ids = [str(user.id)]
    t.target_group_codes = None
    t.target_role_codes = None
    t.target_filter_expr = None

    try:
        d = await svc.dispatch_template(db, template=t, triggered_by_id=user.id, trigger="manual")
    finally:
        # Restore
        t.target_all = original_all
        t.target_user_ids = original_users
        t.target_group_codes = original_groups
        t.target_role_codes = original_roles
        t.target_filter_expr = original_filter
        await db.commit()

    return DispatchRead.model_validate(d)


# ════════════════════════════════════════════════════════════
#   Dispatch history + analytics
# ════════════════════════════════════════════════════════════

@admin_router.get("/templates/{template_id}/dispatches", response_model=DispatchListResponse)
async def list_dispatches(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    rows = (await db.execute(
        select(AdminBroadcastDispatch)
        .where(AdminBroadcastDispatch.template_id == template_id)
        .order_by(AdminBroadcastDispatch.dispatched_at.desc())
        .limit(100),
    )).scalars().all()
    return DispatchListResponse(items=[DispatchRead.model_validate(r) for r in rows], total=len(rows))


@admin_router.get("/templates/{template_id}/analytics", response_model=BroadcastAnalytics)
async def analytics(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("notifications.broadcast")),
):
    t = await db.get(AdminBroadcastTemplate, template_id)
    if not t: raise HTTPException(404, "Not found")
    res = await svc.analytics_for_template(db, t)
    return BroadcastAnalytics(**res)


# ════════════════════════════════════════════════════════════
#   Recipient-facing endpoints (any authenticated user)
# ════════════════════════════════════════════════════════════

@user_router.get("/sticky", response_model=list[StickyNotification])
async def my_sticky(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return all pending sticky notifications for the current user.

    Frontend mounts a global modal that subscribes to this; loops while
    `acknowledged_at IS NULL`.
    """
    rows = (await db.execute(
        select(Notification).where(and_(
            Notification.recipient_user_id == user.id,
            Notification.is_sticky.is_(True),
            Notification.acknowledged_at.is_(None),
            or_(
                Notification.expires_at.is_(None),
                Notification.expires_at > datetime.now(timezone.utc),
            ),
            Notification.is_archived.is_(False),
        )).order_by(Notification.created_at.asc()),
    )).scalars().all()
    return [StickyNotification.model_validate(r) for r in rows]


@user_router.post("/{notification_id}/ack", response_model=AckRead)
async def ack(
    notification_id: UUID,
    body: AckSubmit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = await db.get(Notification, notification_id)
    if not n: raise HTTPException(404, "Not found")
    try:
        a = await svc.acknowledge_notification(
            db, notification=n, user=user,
            response_text=body.response_text,
            response_value=body.response_value,
            response_file=body.response_file,
        )
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return AckRead.model_validate(a)
