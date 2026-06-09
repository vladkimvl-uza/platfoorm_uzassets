"""Notifications API — thin HTTP layer (refactored 2026-05-25).

State-changing endpoints (mark_read / archive / send / broadcast) delegate
to the existing core `app/services/notifications_service.py` (used by all
other modules to deliver notifications).

WebSocket endpoint is kept inline — transport-specific concerns.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jwt as app_jwt
from app.core.security import get_current_user, require_permission
from app.database import AsyncSessionLocal, get_db
from app.dependencies.notifications import NotificationsQueryServiceDep
from app.models.user import User
from app.schemas.notification import (
    NotificationBroadcast,
    NotificationBulkAction,
    NotificationCreate,
    NotificationListResponse,
    NotificationPreferenceRead,
    NotificationPreferencesBulk,
    NotificationRead,
    NotificationTypesResponse,
    UnreadCountResponse,
)
from app.services.notifications_service import (
    archive,
    broadcast,
    mark_all_read,
    mark_read,
    mark_read_by_filter,
    notifications_ws_manager,
    notify,
    unread_count,
    unread_count_detail,
)

from pydantic import BaseModel  # noqa: E402

router = APIRouter(prefix="/notifications", tags=["notifications"])
log = logging.getLogger(__name__)


class ReadByFilter(BaseModel):
    """Фильтр пометки-прочитанным секции сайдбара. types — точные типы или
    префиксы с точкой ('watch.' → все watch.*); modules — source_module."""
    types: list[str] = []
    modules: list[str] = []


# ─── Feed & counts ────────────────────────────────────────────────

@router.get("/feed", response_model=NotificationListResponse)
async def feed(
    service: NotificationsQueryServiceDep,
    unread_only: bool = Query(False),
    types: Optional[list[str]] = Query(None),
    priorities: Optional[list[str]] = Query(None),
    include_archived: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    return await service.feed(
        user_id=user.id, unread_only=unread_only,
        types=types, priorities=priorities,
        include_archived=include_archived,
        page=page, per_page=per_page,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return UnreadCountResponse(**(await unread_count_detail(db, user.id)))


# ─── Mark read / archive ──────────────────────────────────────────

@router.post("/{notification_id}/read")
async def post_read_one(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cnt = await mark_read(db, user.id, [notification_id])
    return {"updated": cnt}


@router.post("/read-bulk")
async def post_read_bulk(
    body: NotificationBulkAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cnt = await mark_read(db, user.id, body.ids)
    return {"updated": cnt}


@router.post("/read-all")
async def post_read_all(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cnt = await mark_all_read(db, user.id)
    return {"updated": cnt}


@router.post("/read-by")
async def post_read_by(
    body: ReadByFilter,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Пометить прочитанными уведомления секции (по type-префиксам / модулям).
    Вызывается при заходе в раздел сайдбара — счётчик-бейдж гаснет."""
    cnt = await mark_read_by_filter(
        db, user.id, type_prefixes=body.types, modules=body.modules,
    )
    return {"updated": cnt}


@router.post("/{notification_id}/archive")
async def post_archive_one(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cnt = await archive(db, user.id, [notification_id])
    return {"archived": cnt}


@router.post("/archive-bulk")
async def post_archive_bulk(
    body: NotificationBulkAction,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cnt = await archive(db, user.id, body.ids)
    return {"archived": cnt}


# ─── Preferences ──────────────────────────────────────────────────

@router.get("/preferences", response_model=list[NotificationPreferenceRead])
async def list_prefs(
    service: NotificationsQueryServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.list_preferences(user.id)


@router.put("/preferences", response_model=list[NotificationPreferenceRead])
async def update_prefs(
    body: NotificationPreferencesBulk,
    service: NotificationsQueryServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.upsert_preferences(
        user_id=user.id, preferences=body.preferences,
    )


# ─── Types catalog ────────────────────────────────────────────────

@router.get("/types", response_model=NotificationTypesResponse)
async def list_types(
    service: NotificationsQueryServiceDep,
    _u: User = Depends(get_current_user),
):
    return service.list_types()


# ─── Single notification (MUST come after literal-prefix routes) ──

@router.get("/{notification_id}", response_model=NotificationRead)
async def get_one(
    notification_id: UUID,
    service: NotificationsQueryServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.get_one(notification_id, user_id=user.id)


# ─── Send / Broadcast (admin) ─────────────────────────────────────

@router.post("/send", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
async def send_one(
    body: NotificationCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("notifications.send")),
):
    n = await notify(
        db,
        recipient_id=body.recipient_user_id,
        type=body.type, title=body.title, body=body.body,
        priority=body.priority, payload=body.payload, link_url=body.link_url,
        source_module=body.source_module, source_entity_id=body.source_entity_id,
        source_user_id=actor.id, expires_at=body.expires_at,
    )
    if not n:
        raise HTTPException(status.HTTP_409_CONFLICT, "Recipient has muted this notification type")
    return NotificationRead.model_validate(n)


@router.post("/broadcast")
async def post_broadcast(
    body: NotificationBroadcast,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("notifications.admin")),
):
    delivered = await broadcast(
        db,
        type=body.type, title=body.title, body=body.body,
        priority=body.priority, link_url=body.link_url,
        target_role_codes=body.target_role_codes,
        target_group_codes=body.target_group_codes,
        target_user_ids=body.target_user_ids,
        target_all=body.target_all, actor=actor,
    )
    return {"delivered": delivered}


@router.post("/test")
async def post_test(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = await notify(
        db, recipient_id=user.id, type="system.announcement",
        title="Тестовое уведомление",
        body="Если вы это видите — система уведомлений работает корректно.",
        priority="normal", source_user_id=user.id,
    )
    return {"sent": bool(n), "id": str(n.id) if n else None}


# ─── WebSocket ────────────────────────────────────────────────────

@router.websocket("/ws/{token}")
async def websocket_endpoint(ws: WebSocket, token: str):
    """Live notifications via WS. Token in URL path (browser can't set headers)."""
    try:
        payload = app_jwt.decode_token(token, expected_type="access")
        user_id = UUID(payload["sub"])
    except Exception:
        try:
            await ws.close(code=4401)
        except Exception:
            pass
        return

    await ws.accept()
    await notifications_ws_manager.connect(user_id, ws)

    try:
        async with AsyncSessionLocal() as db:
            cnt = await unread_count(db, user_id)
        await ws.send_json({
            "event":        "notification.unread_count",
            "unread_count": cnt,
            "timestamp":    datetime.now(UTC).isoformat(),
        })
    except Exception as e:
        log.warning("WS initial push failed: %s", e)

    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=60.0)
            except TimeoutError:
                await ws.send_json({
                    "event":     "system.ping",
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                continue

            mtype = msg.get("type")
            if mtype == "ping":
                await ws.send_json({
                    "event":     "system.ping",
                    "timestamp": datetime.now(UTC).isoformat(),
                })
            elif mtype == "mark_read":
                ids = msg.get("ids") or []
                if ids:
                    try:
                        async with AsyncSessionLocal() as db:
                            uuids = [UUID(i) for i in ids]
                            await mark_read(db, user_id, uuids)
                    except Exception as e:
                        log.warning("WS mark_read failed: %s", e)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.warning("WS error user=%s: %s", user_id, e)
    finally:
        await notifications_ws_manager.disconnect(user_id, ws)


@router.get("/ws/stats")
async def ws_stats(
    _u: User = Depends(require_permission("notifications.admin")),
):
    return notifications_ws_manager.stats()
