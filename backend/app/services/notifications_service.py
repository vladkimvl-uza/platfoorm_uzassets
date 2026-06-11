"""Notifications service + WebSocket connection manager (Pack 11.0).

Public API:
  * await notify(db, recipient, type, title, ...)        — create + dispatch
  * await broadcast(db, type, title, target_*, ...)      — many recipients
  * await mark_read(db, user, ids)                       — flip is_read
  * await unread_count(db, user)                         — quick count for badge
  * notifications_ws_manager                              — singleton
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import WebSocket
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NOTIFICATION_TYPES, Notification, NotificationPreference
from app.models.user import Group, Role, User

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#   WebSocket connection manager (per-user, multi-tab safe)
# ════════════════════════════════════════════════════════════

class _WSManager:
    """Tracks active WebSocket connections per user.

    One user can have many connections (multiple browser tabs / devices).
    Broadcast to a user fans out to all their connections.
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, ws: WebSocket) -> None:
        async with self._lock:
            self._connections[user_id].append(ws)
        log.info("WS connected: user=%s total_for_user=%d total_overall=%d",
                 user_id, len(self._connections[user_id]),
                 sum(len(v) for v in self._connections.values()))

    async def disconnect(self, user_id: UUID, ws: WebSocket) -> None:
        async with self._lock:
            if user_id in self._connections:
                try:
                    self._connections[user_id].remove(ws)
                except ValueError:
                    pass
                if not self._connections[user_id]:
                    del self._connections[user_id]
        log.info("WS disconnected: user=%s", user_id)

    async def send_to_user(self, user_id: UUID, payload: dict[str, Any]) -> int:
        """Send to ALL active connections of a user. Returns number of recipients reached."""
        sent = 0
        dead: list[WebSocket] = []
        async with self._lock:
            conns = list(self._connections.get(user_id, []))
        for ws in conns:
            try:
                await ws.send_text(json.dumps(payload, default=str))
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_id, ws)
        return sent

    def is_online(self, user_id: UUID) -> bool:
        return bool(self._connections.get(user_id))

    def online_users(self) -> list[UUID]:
        return list(self._connections.keys())

    def stats(self) -> dict[str, int]:
        return {
            "users_online": len(self._connections),
            "connections":  sum(len(v) for v in self._connections.values()),
        }


# Singleton — imported across the app
notifications_ws_manager = _WSManager()


# ════════════════════════════════════════════════════════════
#   Core notify
# ════════════════════════════════════════════════════════════

def _resolve_priority(notif_type: str, override: Optional[str]) -> str:
    if override:
        return override
    meta = NOTIFICATION_TYPES.get(notif_type)
    return meta["priority"] if meta else "normal"


async def _user_wants_in_app(db: AsyncSession, user_id: UUID, notif_type: str) -> bool:
    """Check user preference for `in_app` channel. Default = True."""
    pref = (await db.execute(
        select(NotificationPreference).where(and_(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notif_type,
        )),
    )).scalar_one_or_none()
    if pref is None:
        return True
    if pref.is_muted:
        # Mute timeout?
        if pref.mute_until and pref.mute_until < datetime.now(UTC):
            return True
        return False
    return bool(pref.channels.get("in_app", True))


# Удерживаем ссылки на фоновые email-таски, чтобы их не собрал GC.
_EMAIL_BG_TASKS: set = set()


# Типы, у которых e-mail ВЫКЛЮЧЕН по умолчанию (слишком шумно для почты).
# Пользователь может включить вручную в настройках уведомлений. Остальные
# типы по умолчанию шлются на почту (default True).
_EMAIL_OFF_BY_DEFAULT = {"task.status_changed", "project.status_changed", "watch.status"}


async def _user_wants_email(db: AsyncSession, user_id: UUID, notif_type: str) -> bool:
    """Дублировать ли уведомление на email. Default зависит от типа: статусные
    смены — выкл по умолчанию, остальные — вкл. Явная настройка пользователя
    (channels.email) всегда побеждает дефолт."""
    default_email = notif_type not in _EMAIL_OFF_BY_DEFAULT
    pref = (await db.execute(
        select(NotificationPreference).where(and_(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notif_type,
        )),
    )).scalar_one_or_none()
    if pref is None:
        return default_email
    if pref.is_muted and not (pref.mute_until and pref.mute_until < datetime.now(UTC)):
        return False
    return bool(pref.channels.get("email", default_email))


async def user_wants_telegram(db: AsyncSession, user_id: UUID, notif_type: str) -> bool:
    """Per-type opt-out для Telegram (поверх UserTelegramPref-категорий).
    Default True — существующее поведение не меняется; пользователь может
    выключить конкретный тип в настройках (channels.telegram=false).
    Статусные смены — выкл по умолчанию (как и email)."""
    default_tg = notif_type not in _EMAIL_OFF_BY_DEFAULT
    pref = (await db.execute(
        select(NotificationPreference).where(and_(
            NotificationPreference.user_id == user_id,
            NotificationPreference.notification_type == notif_type,
        )),
    )).scalar_one_or_none()
    if pref is None:
        return default_tg
    if pref.is_muted and not (pref.mute_until and pref.mute_until < datetime.now(UTC)):
        return False
    return bool(pref.channels.get("telegram", default_tg))


async def _forward_notification_email(
    db: AsyncSession, *, recipient_id: UUID, type: str, title: str,
    body: Optional[str], priority: str, source_module: Optional[str],
    link_url: Optional[str],
) -> None:
    """Best-effort дублирование уведомления на email. MFA-коды — НЕ шлём
    на почту (только Telegram, по требованию)."""
    import asyncio
    if type in ("mfa", "mfa_code", "access_code"):
        return
    if not await _user_wants_email(db, recipient_id, type):
        return
    from sqlalchemy import select as _sel
    from app.models.user import User as _User
    row = (await db.execute(
        _sel(_User.email, _User.full_name).where(_User.id == recipient_id)
    )).first()
    if not row or not row.email:
        return
    from app.services.email.service import email_configured
    if not email_configured():
        return
    from app.services.email import templates as _tpl
    from app.services.email.runtime_config import effective
    # Абсолютная ссылка для кнопки.
    url = link_url
    if url and url.startswith("/"):
        url = str(effective().get("PUBLIC_URL") or "").rstrip("/") + url
    accent = "#E24B4A" if priority in ("high", "critical") else "#534AB7"
    subj, html = _tpl.notification_email(
        eyebrow=source_module or "Уведомление", title=title,
        lines=[body] if body else ["Откройте платформу для деталей."],
        action_label=("Открыть в платформе" if url else None),
        action_url=(url if url else None), accent=accent,
    )
    from app.services.email.service import send_email
    t = asyncio.create_task(send_email(row.email, subj, html))
    _EMAIL_BG_TASKS.add(t)
    t.add_done_callback(_EMAIL_BG_TASKS.discard)


async def notify(
    db: AsyncSession,
    *,
    recipient_id: UUID,
    type: str,
    title: str,
    body: Optional[str] = None,
    priority: Optional[str] = None,
    payload: Optional[dict] = None,
    link_url: Optional[str] = None,
    source_module: Optional[str] = None,
    source_entity_id: Optional[str] = None,
    source_user_id: Optional[UUID] = None,
    company_id: Optional[UUID] = None,
    expires_at: Optional[datetime] = None,
    commit: bool = True,
    in_app_only: bool = False,
) -> Optional[Notification]:
    """Create and dispatch one notification.

    Returns None if user has muted this type.
    Caller must NOT pass an already-committed session if `commit=False`.

    `in_app_only=True` skips Telegram + e-mail forwarding (used for high-volume
    feeds like the owner activity stream, which would otherwise spam channels).
    """
    if not await _user_wants_in_app(db, recipient_id, type):
        return None

    prio = _resolve_priority(type, priority)

    n = Notification(
        recipient_user_id=recipient_id,
        type=type,
        priority=prio,
        title=title,
        body=body,
        payload=payload,
        link_url=link_url,
        source_module=source_module,
        source_entity_id=source_entity_id,
        source_user_id=source_user_id,
        company_id=company_id,
        expires_at=expires_at,
        is_read=False,
        is_archived=False,
        created_at=datetime.now(UTC),
        delivered_channels={"in_app": True},
    )
    db.add(n)
    await db.flush()

    if commit:
        await db.commit()
        if not in_app_only:
            # .3: fire-and-forget TG forward (own DB session, never blocks)
            try:
                from app.services.telegram_notify_hook_bg import schedule_forward
                schedule_forward(str(n.id))
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning('tg-forward schedule failed: %s', _e)
            # E-mail-канал: дублируем уведомление на почту (best-effort, кроме MFA).
            try:
                await _forward_notification_email(
                    db, recipient_id=recipient_id, type=type, title=title, body=body,
                    priority=prio, source_module=source_module, link_url=link_url,
                )
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning('email-forward failed: %s', _e)
        await db.refresh(n)

    # Best-effort WS push (failure shouldn't break notify())
    try:
        await notifications_ws_manager.send_to_user(recipient_id, {
            "event": "notification.new",
            "notification": {
                "id":           str(n.id),
                "created_at":   n.created_at.isoformat(),
                "type":         n.type,
                "priority":     n.priority,
                "title":        n.title,
                "body":         n.body,
                "payload":      n.payload,
                "link_url":     n.link_url,
                "source_module": n.source_module,
                "source_entity_id": n.source_entity_id,
                "source_user_id": str(n.source_user_id) if n.source_user_id else None,
                "is_read":      False,
                "is_archived":  False,
            },
            "timestamp":     datetime.now(UTC).isoformat(),
        })
        # Also push updated count
        cnt = await unread_count(db, recipient_id)
        await notifications_ws_manager.send_to_user(recipient_id, {
            "event":        "notification.unread_count",
            "unread_count": cnt,
            "timestamp":    datetime.now(UTC).isoformat(),
        })
    except Exception as e:
        log.warning("WS push failed for user=%s type=%s: %s", recipient_id, type, e)

    return n


async def broadcast(
    db: AsyncSession,
    *,
    type: str,
    title: str,
    body: Optional[str] = None,
    priority: str = "normal",
    link_url: Optional[str] = None,
    target_role_codes: Optional[list[str]] = None,
    target_group_codes: Optional[list[str]] = None,
    target_user_ids: Optional[list[UUID]] = None,
    target_all: bool = False,
    actor: Optional[User] = None,
) -> int:
    """Broadcast to multiple users. Returns # delivered."""
    recipient_ids: set[UUID] = set()

    if target_all:
        rows = (await db.execute(
            select(User.id).where(User.is_active.is_(True)),
        )).all()
        recipient_ids.update(r[0] for r in rows)
    else:
        if target_user_ids:
            recipient_ids.update(target_user_ids)
        if target_role_codes:
            rows = (await db.execute(
                select(User.id)
                .join(User.roles)
                .where(and_(User.is_active.is_(True), Role.code.in_(target_role_codes))),
            )).all()
            recipient_ids.update(r[0] for r in rows)
        if target_group_codes:
            rows = (await db.execute(
                select(User.id)
                .join(User.groups)
                .where(and_(User.is_active.is_(True), Group.code.in_(target_group_codes))),
            )).all()
            recipient_ids.update(r[0] for r in rows)

    sent = 0
    for uid in recipient_ids:
        n = await notify(
            db, recipient_id=uid, type=type, title=title, body=body,
            priority=priority, link_url=link_url,
            source_user_id=actor.id if actor else None,
            commit=False,
        )
        if n:
            sent += 1
    await db.commit()
    return sent


# ════════════════════════════════════════════════════════════
#   Queries
# ════════════════════════════════════════════════════════════

async def unread_count(db: AsyncSession, user_id: UUID) -> int:
    return (await db.execute(
        select(func.count(Notification.id)).where(and_(
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
            Notification.is_archived.is_(False),
        )),
    )).scalar() or 0


async def unread_count_detail(db: AsyncSession, user_id: UUID) -> dict:
    """Counts grouped by priority, type и module для разбивки бейджа.

    Один проход (GROUP BY по всем трём полям + свёртка в Python) вместо трёх
    отдельных запросов — эндпоинт поллится каждые 30с каждым клиентом, так что
    экономия round-trip'ов масштабируется на всех пользователей. Тот же индекс
    по (recipient_user_id, is_read, is_archived) драйвит WHERE.
    """
    rows = (await db.execute(
        select(
            Notification.priority,
            Notification.type,
            Notification.source_module,
            Notification.company_id,
            func.count(Notification.id),
        )
        .where(and_(
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
            Notification.is_archived.is_(False),
        ))
        .group_by(Notification.priority, Notification.type, Notification.source_module, Notification.company_id),
    )).all()

    by_priority: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_module: dict[str, int] = {}
    by_company: dict[str, int] = {}
    total = 0
    for prio, typ, module, company_id, cnt in rows:
        total += cnt
        if prio:
            by_priority[prio] = by_priority.get(prio, 0) + cnt
        if typ:
            by_type[typ] = by_type.get(typ, 0) + cnt
        if module:
            by_module[module] = by_module.get(module, 0) + cnt
        if company_id:
            key = str(company_id)
            by_company[key] = by_company.get(key, 0) + cnt

    return {
        "count": total,
        "by_priority": by_priority,
        "by_type": by_type,
        "by_module": by_module,
        "by_company": by_company,
    }


async def mark_read(db: AsyncSession, user_id: UUID, ids: list[UUID]) -> int:
    if not ids:
        return 0
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(and_(
            Notification.recipient_user_id == user_id,
            Notification.id.in_(ids),
            Notification.is_read.is_(False),
        ))
        .values(is_read=True, read_at=now),
    )
    await db.commit()
    cnt = result.rowcount or 0
    # Push updated count to all user's WS tabs
    try:
        new_count = await unread_count(db, user_id)
        await notifications_ws_manager.send_to_user(user_id, {
            "event":        "notification.unread_count",
            "unread_count": new_count,
            "timestamp":    now.isoformat(),
        })
    except Exception:
        pass
    return cnt


async def mark_all_read(db: AsyncSession, user_id: UUID) -> int:
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(and_(
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
        ))
        .values(is_read=True, read_at=now),
    )
    await db.commit()
    cnt = result.rowcount or 0
    try:
        await notifications_ws_manager.send_to_user(user_id, {
            "event":        "notification.unread_count",
            "unread_count": 0,
            "timestamp":    now.isoformat(),
        })
    except Exception:
        pass
    return cnt


async def mark_read_by_filter(
    db: AsyncSession,
    user_id: UUID,
    *,
    type_prefixes: Optional[list[str]] = None,
    modules: Optional[list[str]] = None,
    company_ids: Optional[list[str]] = None,
) -> int:
    """Пометить прочитанными непрочитанные уведомления, попадающие под фильтр
    секции сайдбара: тип с префиксом (напр. 'watch.' → все watch.*), точный тип,
    source_module или company_id. Используется при заходе в раздел/компанию —
    бейдж гаснет."""
    type_prefixes = type_prefixes or []
    modules = modules or []
    company_ids = company_ids or []
    if not type_prefixes and not modules and not company_ids:
        return 0

    conds = []
    for t in type_prefixes:
        if t.endswith("."):
            conds.append(Notification.type.like(f"{t}%"))
        else:
            conds.append(Notification.type == t)
    if modules:
        conds.append(Notification.source_module.in_(modules))
    if company_ids:
        conds.append(Notification.company_id.in_(company_ids))
    if not conds:
        return 0

    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(and_(
            Notification.recipient_user_id == user_id,
            Notification.is_read.is_(False),
            or_(*conds),
        ))
        .values(is_read=True, read_at=now),
    )
    await db.commit()
    cnt = result.rowcount or 0
    if cnt:
        try:
            new_count = await unread_count(db, user_id)
            await notifications_ws_manager.send_to_user(user_id, {
                "event":        "notification.unread_count",
                "unread_count": new_count,
                "timestamp":    now.isoformat(),
            })
        except Exception:
            pass
    return cnt


async def archive(db: AsyncSession, user_id: UUID, ids: list[UUID]) -> int:
    if not ids:
        return 0
    now = datetime.now(UTC)
    result = await db.execute(
        update(Notification)
        .where(and_(
            Notification.recipient_user_id == user_id,
            Notification.id.in_(ids),
        ))
        .values(is_archived=True, archived_at=now, is_read=True, read_at=now),
    )
    await db.commit()
    return result.rowcount or 0
