"""Notifications API — thin HTTP layer (refactored 2026-05-25).

State-changing endpoints (mark_read / archive / send / broadcast) delegate
to the existing core `app/services/notifications_service.py` (used by all
other modules to deliver notifications).

WebSocket endpoint is kept inline — transport-specific concerns.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional
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
from sqlalchemy import select
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
# Separate router for the WebSocket, mounted in main.py WITHOUT the router-level
# capture_activity dependency: that dep declares `request: Request`, which FastAPI
# cannot resolve in a WebSocket scope → every /notifications/ws connect raised
# "capture_activity() missing 'request'" and the live-push socket 500'd (client
# fell back to polling). Mirrors app.api.routes.company_library.ws_router.
ws_router = APIRouter()
log = logging.getLogger(__name__)


class ReadByFilter(BaseModel):
    """Фильтр пометки-прочитанным секции сайдбара. types — точные типы или
    префиксы с точкой ('watch.' → все watch.*); modules — source_module;
    company_ids — привязка к компании (заход в карточку компании)."""
    types: list[str] = []
    modules: list[str] = []
    company_ids: list[str] = []


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
        company_ids=body.company_ids,
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


# ─── Field-level detail «что кто где изменял» (из журнала аудита) ──────
# По клику на уведомление подтягиваем ближайшую запись аудита той же
# сущности → показываем структурный diff (было→стало / поля). Без новых
# уведомлений, объём не растёт. Scope: только получатель этого уведомления,
# только сущность, о которой оно (entity_id-match) — детали того, о чём
# пользователя уже уведомили.

_AUDIT_ACTION_LABELS: dict[str, str] = {
    "create": "Создание", "update": "Изменение", "delete": "Удаление",
    "save": "Сохранение", "import": "Импорт", "approve": "Согласование",
    "reject": "Отклонение", "assign": "Назначение", "grant": "Выдача прав",
    "revoke": "Отзыв прав",
}
_MODULE_LABELS: dict[str, str] = {
    "kpi": "KPI", "bp": "Бизнес-план", "business_plan": "Бизнес-план",
    "governance": "Корп. управление", "esg": "ESG", "financials": "Финансы",
    "finance": "Финансы", "procurement": "Закупки", "ratings": "Рейтинги",
    "admin": "Админка", "rbac": "RBAC", "auth": "Вход и сессии", "tasks": "Задачи",
    "companies": "Компании", "investment": "Инвест-проекты",
}


def _fld_label(k: str) -> str:
    from app.services.audit_field_labels import field_label
    return field_label(k)


def _fmt_val(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "да" if v else "нет"
    if isinstance(v, (list, tuple)):
        s = ", ".join(_fmt_val(x) for x in v[:12])
        return s + (f" … (+{len(v) - 12})" if len(v) > 12 else "") or "—"
    if isinstance(v, dict):
        import json as _j
        return _j.dumps(v, ensure_ascii=False)[:200]
    s = str(v)
    return s[:300] if len(s) > 300 else s


class AuditChangeRow(BaseModel):
    label: str
    old: Optional[str] = None
    new: Optional[str] = None
    value: Optional[str] = None   # плоское поле без пары было→стало


class NotificationAuditDetail(BaseModel):
    found: bool = False
    action: Optional[str] = None
    action_label: Optional[str] = None
    module: Optional[str] = None
    module_label: Optional[str] = None
    section: Optional[str] = None       # конкретный раздел («Финансы · НСБУ»)
    table: Optional[str] = None         # таблица/сущность («Компания», «Роль»)
    entity_type: Optional[str] = None
    entity_label: Optional[str] = None
    actor_name: Optional[str] = None
    notes: Optional[str] = None
    at: Optional[datetime] = None
    changes: list[AuditChangeRow] = []


_OLDNEW_KEYS = (("old", "new"), ("from", "to"), ("before", "after"), ("prev", "next"))


def _pair_oldnew(v: dict) -> Optional[tuple[Any, Any]]:
    """Если значение — пара «было→стало», вернуть (old, new)."""
    for ok, nk in _OLDNEW_KEYS:
        if ok in v or nk in v:
            return v.get(ok), v.get(nk)
    return None


def _normalize_diff(diff: Optional[dict]) -> list[AuditChangeRow]:
    """Разбор произвольного diff-словаря аудита в строки для модалки.
    Три формы: значение-пара {old,new}; верхний уровень {old:{…},new:{…}};
    иначе — плоские поле→значение."""
    if not isinstance(diff, dict) or not diff:
        return []
    rows: list[AuditChangeRow] = []
    # форма 2: {"old": {...}, "new": {...}} — сопоставляем по ключам
    top = _pair_oldnew(diff)
    if top is not None and isinstance(top[0], dict) and isinstance(top[1], dict):
        old_d, new_d = top
        for k in sorted(set(old_d) | set(new_d)):
            if old_d.get(k) == new_d.get(k):
                continue
            rows.append(AuditChangeRow(label=_fld_label(k),
                                       old=_fmt_val(old_d.get(k)), new=_fmt_val(new_d.get(k))))
        return rows
    # формы 1 и 3
    for k, v in diff.items():
        if isinstance(v, dict):
            pair = _pair_oldnew(v)
            if pair is not None:
                rows.append(AuditChangeRow(label=_fld_label(k),
                                           old=_fmt_val(pair[0]), new=_fmt_val(pair[1])))
                continue
        rows.append(AuditChangeRow(label=_fld_label(k), value=_fmt_val(v)))
    return rows


@router.get("/{notification_id}/audit-detail", response_model=NotificationAuditDetail)
async def get_notification_audit_detail(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Field-level детали изменения, о котором уведомили (из журнала аудита)."""
    from app.models.audit import AuditLog
    from app.models.notification import Notification

    n = (await db.execute(select(Notification).where(
        Notification.id == notification_id,
        Notification.recipient_user_id == user.id,
    ))).scalar_one_or_none()
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")

    sid = n.source_entity_id
    if not sid:
        return NotificationAuditDetail(found=False)

    # Запись аудита того же изменения в окне вокруг времени уведомления
    # (аудит пишется за микросекунды ДО notify). Предпочитаем того же автора.
    #
    # ВАЖНО: у уведомлений ленты активности (owner.activity) source_entity_id —
    # это HTTP-ПУТЬ запроса, а не id сущности (см. owner_activity.notify_owners_
    # of_change). Раньше сопоставление шло только по AuditLog.entity_id → для
    # всей ленты активности блок «Что изменилось» не находился никогда.
    hi = (n.created_at or datetime.now(UTC)) + timedelta(seconds=30)
    if str(sid).startswith("/"):
        lo = (n.created_at or datetime.now(UTC)) - timedelta(minutes=5)
        base = select(AuditLog).where(
            AuditLog.http_path == str(sid),
            AuditLog.created_at <= hi,
            AuditLog.created_at >= lo,
        )
    else:
        base = select(AuditLog).where(
            AuditLog.entity_id == str(sid),
            AuditLog.created_at <= hi,
        )
    row = None
    if n.source_user_id is not None:
        row = (await db.execute(
            base.where(AuditLog.actor_id == n.source_user_id)
                .order_by(AuditLog.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    if row is None:
        row = (await db.execute(
            base.order_by(AuditLog.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    if row is None:
        return NotificationAuditDetail(found=False)

    # Имя автора — из users (fallback на actor_email из строки аудита)
    actor_name: Optional[str] = None
    if row.actor_id is not None:
        actor_name = (await db.execute(
            select(User.full_name).where(User.id == row.actor_id)
        )).scalar_one_or_none()
    actor_name = actor_name or row.actor_email

    act = (row.action or "").lower()
    action_label = next((lbl for key, lbl in _AUDIT_ACTION_LABELS.items() if key in act), row.action)
    mod = row.module or n.source_module
    from app.services.audit_service import (
        _TABLE_LABELS,
        _section_from_action,
        _section_from_path,
    )
    return NotificationAuditDetail(
        found=True,
        action=row.action,
        action_label=action_label,
        module=mod,
        module_label=_MODULE_LABELS.get(mod or "", mod),
        section=(_section_from_path(row.http_path) or _MODULE_LABELS.get(mod or "", None)
                 or _section_from_action(row.action)),
        table=_TABLE_LABELS.get(row.entity_type or "", None),
        entity_type=row.entity_type,
        entity_label=row.entity_label,
        actor_name=actor_name,
        notes=row.notes,
        at=row.created_at,
        changes=_normalize_diff(row.diff),
    )


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
        title_template="Тестовое уведомление",
        body_template="Если вы это видите — система уведомлений работает корректно.",
        priority="normal", source_user_id=user.id,
    )
    return {"sent": bool(n), "id": str(n.id) if n else None}


# ─── WebSocket ────────────────────────────────────────────────────

_WS_TICKET_PROTO = "uza-ws-ticket-v1"


@router.post("/ws-ticket")
async def post_ws_ticket(user: User = Depends(get_current_user)):
    """Выдаёт 30-сек тикет для WS уведомлений. Аутентификация — обычный
    Authorization-заголовок. Тикет уходит в Sec-WebSocket-Protocol (не в URL) →
    не попадает в логи/history/Referer (в отличие от access-JWT в пути)."""
    return {"ticket": app_jwt.create_ws_ticket(subject=str(user.id)), "expires_in": 30}


@ws_router.websocket("/notifications/ws")
async def websocket_endpoint(ws: WebSocket):
    """Live-уведомления через WS. Клиент предлагает субпротоколы
    ["uza-ws-ticket-v1", "<ws_ticket>"] — тикет из POST /ws-ticket."""
    protos = ws.scope.get("subprotocols") or []
    ticket = protos[1] if len(protos) >= 2 and protos[0] == _WS_TICKET_PROTO else None
    if not ticket:
        try:
            await ws.close(code=4401)
        except Exception:
            pass
        return
    try:
        payload = app_jwt.decode_token(ticket, expected_type="ws_ticket")
        user_id = UUID(payload["sub"])
    except Exception:
        try:
            await ws.close(code=4401)
        except Exception:
            pass
        return

    await ws.accept(subprotocol=_WS_TICKET_PROTO)
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
