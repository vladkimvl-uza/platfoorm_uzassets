"""Notifications routes (Pack 11.0).

REST under /notifications/*.
WebSocket at /notifications/ws/{token} — pass JWT in path (browser can't set headers).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import (
    APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status,
)
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import jwt as app_jwt
from app.core.security import get_current_user, require_permission
from app.database import AsyncSessionLocal, get_db
from app.models.notification import NOTIFICATION_TYPES, Notification, NotificationPreference
from app.models.user import User
from app.schemas.notification import (
    NotificationBroadcast,
    NotificationBulkAction,
    NotificationCreate,
    NotificationListResponse,
    NotificationPreferenceRead,
    NotificationPreferenceUpdate,
    NotificationPreferencesBulk,
    NotificationRead,
    NotificationTypeInfo,
    NotificationTypesResponse,
    UnreadCountResponse,
)
from app.services.notifications_service import (
    archive,
    broadcast,
    mark_all_read,
    mark_read,
    notifications_ws_manager,
    notify,
    unread_count,
    unread_count_detail,
)


router = APIRouter(prefix="/notifications", tags=["notifications"])
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#   Feed & counts
# ════════════════════════════════════════════════════════════

@router.get("/feed", response_model=NotificationListResponse)
async def feed(
    unread_only: bool = Query(False),
    types: Optional[list[str]] = Query(None),
    priorities: Optional[list[str]] = Query(None),
    include_archived: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Paginated personal feed. Newest first."""
    base = select(Notification).where(Notification.recipient_user_id == user.id)
    if not include_archived:
        base = base.where(Notification.is_archived.is_(False))
    if unread_only:
        base = base.where(Notification.is_read.is_(False))
    if types:
        base = base.where(Notification.type.in_(types))
    if priorities:
        base = base.where(Notification.priority.in_(priorities))

    total = (await db.execute(
        select(func.count()).select_from(base.subquery()),
    )).scalar() or 0

    rows = (await db.execute(
        base.order_by(Notification.created_at.desc())
        .limit(per_page).offset((page - 1) * per_page),
    )).scalars().all()

    return NotificationListResponse(
        items=[NotificationRead.model_validate(r) for r in rows],
        total=total,
        unread_count=await unread_count(db, user.id),
        page=page,
        per_page=per_page,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fast endpoint for bell badge / polling fallback."""
    return UnreadCountResponse(**(await unread_count_detail(db, user.id)))


# NOTE: `/{notification_id}` GET перенесён ниже (после /preferences, /types),
# иначе FastAPI матчит "/preferences", "/types" как UUID-параметр → 422 uuid_parsing.


# ════════════════════════════════════════════════════════════
#   Mark read / archive
# ════════════════════════════════════════════════════════════

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


# ════════════════════════════════════════════════════════════
#   Preferences
# ════════════════════════════════════════════════════════════

@router.get("/preferences", response_model=list[NotificationPreferenceRead])
async def list_prefs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id),
    )).scalars().all()
    return [NotificationPreferenceRead.model_validate(r) for r in rows]


@router.put("/preferences", response_model=list[NotificationPreferenceRead])
async def update_prefs(
    body: NotificationPreferencesBulk,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    for p in body.preferences:
        existing = (await db.execute(
            select(NotificationPreference).where(and_(
                NotificationPreference.user_id == user.id,
                NotificationPreference.notification_type == p.notification_type,
            )),
        )).scalar_one_or_none()
        if existing:
            if p.channels is not None:
                existing.channels = p.channels
            if p.is_muted is not None:
                existing.is_muted = p.is_muted
            if p.mute_until is not None:
                existing.mute_until = p.mute_until
            if p.digest_mode is not None:
                existing.digest_mode = p.digest_mode
        else:
            db.add(NotificationPreference(
                user_id=user.id,
                notification_type=p.notification_type,
                channels=p.channels or {"in_app": True},
                is_muted=p.is_muted or False,
                mute_until=p.mute_until,
                digest_mode=p.digest_mode or "none",
            ))
    await db.commit()
    rows = (await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id),
    )).scalars().all()
    return [NotificationPreferenceRead.model_validate(r) for r in rows]


# ════════════════════════════════════════════════════════════
#   Type catalog
# ════════════════════════════════════════════════════════════

CATEGORY_MAP = {
    "moderation": "Модерация",
    "mention":    "Взаимодействие",
    "assignment": "Взаимодействие",
    "comment":    "Взаимодействие",
    "deadline":   "Дедлайны",
    "kpi":        "Метрики",
    "audit":      "Безопасность",
    "rbac":       "Безопасность",
    "system":     "Система",
    "data":       "Система",
    "report":     "Система",
}


@router.get("/types", response_model=NotificationTypesResponse)
async def list_types(
    _u: User = Depends(get_current_user),
):
    """Catalog of supported notification types for preferences UI."""
    items = []
    for code, meta in NOTIFICATION_TYPES.items():
        prefix = code.split(".", 1)[0]
        items.append(NotificationTypeInfo(
            code=code, label=meta["label"], priority=meta["priority"],
            category=CATEGORY_MAP.get(prefix, "Прочее"),
        ))
    cats = sorted(set(i.category for i in items))
    return NotificationTypesResponse(types=items, categories=cats)


# ════════════════════════════════════════════════════════════
#   GET single notification — ОБЯЗАТЕЛЬНО после всех literal-prefix routes
#   (/preferences, /types и т.д.), иначе FastAPI матчит их как UUID-param
# ════════════════════════════════════════════════════════════

@router.get("/{notification_id}", response_model=NotificationRead)
async def get_one(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    n = (await db.execute(
        select(Notification).where(and_(
            Notification.id == notification_id,
            Notification.recipient_user_id == user.id,
        )),
    )).scalar_one_or_none()
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return NotificationRead.model_validate(n)


# ════════════════════════════════════════════════════════════
#   Send / Broadcast (admin)
# ════════════════════════════════════════════════════════════

@router.post("/send", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
async def send_one(
    body: NotificationCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission("notifications.send")),
):
    n = await notify(
        db,
        recipient_id=body.recipient_user_id,
        type=body.type,
        title=body.title,
        body=body.body,
        priority=body.priority,
        payload=body.payload,
        link_url=body.link_url,
        source_module=body.source_module,
        source_entity_id=body.source_entity_id,
        source_user_id=actor.id,
        expires_at=body.expires_at,
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
    """Send a sample notification to yourself. Useful for debugging."""
    n = await notify(
        db, recipient_id=user.id, type="system.announcement",
        title="Тестовое уведомление",
        body="Если вы это видите — система уведомлений работает корректно.",
        priority="normal", source_user_id=user.id,
    )
    return {"sent": bool(n), "id": str(n.id) if n else None}


# ════════════════════════════════════════════════════════════
#   WebSocket — live channel
# ════════════════════════════════════════════════════════════

@router.websocket("/ws/{token}")
async def websocket_endpoint(ws: WebSocket, token: str):
    """WebSocket connection for live notifications.

    Token is passed in the URL path because browser WebSocket API
    cannot set Authorization header. Token format = the regular JWT.

    Frame format (server → client): JSON
      { event: 'notification.new'|'notification.unread_count'|'system.ping',
        notification?: {...}, unread_count?: int, timestamp: ISO8601 }

    Frame format (client → server): JSON
      { type: 'ping' }   ← keepalive, server replies system.ping
      { type: 'mark_read', ids: [...] }
    """
    # Authenticate
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

    # Send initial state
    try:
        async with AsyncSessionLocal() as db:
            cnt = await unread_count(db, user_id)
        await ws.send_json({
            "event":        "notification.unread_count",
            "unread_count": cnt,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        log.warning("WS initial push failed: %s", e)

    # Listen for client messages (ping, mark_read)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=60.0)
            except asyncio.TimeoutError:
                # No message in 60s — send ping to keep connection warm
                await ws.send_json({
                    "event":     "system.ping",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            mtype = msg.get("type")
            if mtype == "ping":
                await ws.send_json({
                    "event":     "system.ping",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
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


# ════════════════════════════════════════════════════════════
#   WS stats (debug / monitoring)
# ════════════════════════════════════════════════════════════

@router.get("/ws/stats")
async def ws_stats(
    _u: User = Depends(require_permission("notifications.admin")),
):
    return notifications_ws_manager.stats()
