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
from sqlalchemy import and_, event, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as _SyncSession

from app.core.i18n import normalize_locale, tr
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


# ════════════════════════════════════════════════════════════
#   WS-пуш строго ПОСЛЕ commit (иначе — фантомные уведомления)
# ════════════════════════════════════════════════════════════
# notify() часто НЕ владеет commit'ом (его делает роут или get_db). Раньше WS
# событие notification.new слалось inline до коммита → при rollback клиент уже
# знал о несуществующей строке. Решение: буферим пуши на сессии (session.info) и
# отправляем их из SQLAlchemy-события after_commit; on after_rollback — сбрасываем.
_WS_BG_TASKS: set = set()


def _buffer_ws_push(db: AsyncSession, recipient_id: UUID, n: Notification) -> None:
    """Ставит notification.new в очередь на сессии — отправится только after_commit."""
    payload = {
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
    }
    db.info.setdefault("pending_ws", []).append((recipient_id, payload))


async def _flush_ws(pending: list) -> None:
    recipients: set = set()
    for uid, payload in pending:            # notification.new — по одному на строку
        recipients.add(uid)
        try:
            await notifications_ws_manager.send_to_user(uid, payload)
        except Exception as e:
            log.warning("WS notification.new failed user=%s: %s", uid, e)
    if not recipients:
        return
    # unread_count — по одному на получателя, из СВЕЖЕЙ (закоммиченной) сессии
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db2:
        for uid in recipients:
            try:
                cnt = await unread_count(db2, uid)
                await notifications_ws_manager.send_to_user(uid, {
                    "event":        "notification.unread_count",
                    "unread_count": cnt,
                    "timestamp":    datetime.now(UTC).isoformat(),
                })
            except Exception as e:
                log.warning("WS unread_count failed user=%s: %s", uid, e)


@event.listens_for(_SyncSession, "after_commit")
def _dispatch_pending_ws(session) -> None:
    pending = session.info.pop("pending_ws", None)
    if not pending:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    t = loop.create_task(_flush_ws(pending))
    _WS_BG_TASKS.add(t)
    t.add_done_callback(_WS_BG_TASKS.discard)


@event.listens_for(_SyncSession, "after_rollback")
def _drop_pending_ws(session) -> None:
    session.info.pop("pending_ws", None)     # откат → никаких фантомных пушей


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
        _sel(_User.email, _User.full_name, _User.ui_locale).where(_User.id == recipient_id)
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
    locale = normalize_locale(row.ui_locale)
    subj, html = _tpl.notification_email(
        eyebrow=tr(source_module or "Уведомление", locale), title=title,
        lines=[body] if body else [tr("Откройте платформу для деталей.", locale)],
        action_label=(tr("Открыть в платформе", locale) if url else None),
        action_url=(url if url else None), accent=accent, locale=locale,
    )
    from app.services.email.service import send_email
    t = asyncio.create_task(send_email(row.email, subj, html, locale=locale))
    _EMAIL_BG_TASKS.add(t)
    t.add_done_callback(_EMAIL_BG_TASKS.discard)


def _safe_link_url(url: Optional[str]) -> Optional[str]:
    """Sanitize a notification link_url before it becomes a CLICKABLE target
    (in-app link / Telegram inline button / e-mail button). Уведомление —
    доверенный канал: непроверенный link_url = вектор stored-XSS (javascript:/
    data:) и фишинга (//evil, произвольный внешний хост через доверенную кнопку).
    Whitelist: только внутренний относительный путь ('/...') или абсолютный
    http(s). Всё прочее (javascript:/data:/vbscript:/file:/protocol-relative
    '//host'/голое слово) → None (кнопка не рисуется)."""
    if not url:
        return None
    s = url.strip()
    if not s:
        return None
    # Внутренний путь — самый частый кейс; НЕ protocol-relative '//host'.
    if s.startswith("/") and not s.startswith("//"):
        return s
    low = s.lower()
    if low.startswith("https://") or low.startswith("http://"):
        return s
    return None


async def _recipient_locale(db: AsyncSession, recipient_id: UUID) -> str:
    """Язык офлайн-уведомления из профиля получателя."""
    raw = (await db.execute(
        select(User.ui_locale).where(User.id == recipient_id),
    )).scalar_one_or_none()
    return normalize_locale(raw)


def _render_system_template(
    template: str,
    locale: str,
    values: Optional[dict[str, Any]],
    translate_vars: Optional[set[str]],
) -> str:
    """Перевести системный шаблон, не меняя пользовательские значения.

    Только имена из ``translate_vars`` считаются системными справочными
    лейблами. Списки переводятся поэлементно и соединяются запятой.
    """
    rendered: dict[str, Any] = dict(values or {})
    for name in translate_vars or set():
        if name not in rendered:
            continue
        value = rendered[name]
        if isinstance(value, (list, tuple)):
            rendered[name] = ", ".join(tr(str(item), locale) for item in value)
        elif value is not None:
            rendered[name] = tr(str(value), locale)
    return tr(template, locale, **rendered)


async def notify(
    db: AsyncSession,
    *,
    recipient_id: UUID,
    type: str,
    title: str,
    body: Optional[str] = None,
    title_template: Optional[str] = None,
    body_template: Optional[str] = None,
    template_vars: Optional[dict[str, Any]] = None,
    translate_vars: Optional[set[str]] = None,
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

    # Системные производители передают шаблоны явно. Обычные title/body
    # (админские рассылки, комментарии, AI direct.message и данные из БД)
    # остаются байт-в-байт такими, какими их ввели.
    if title_template or body_template:
        locale = await _recipient_locale(db, recipient_id)
        if title_template:
            title = _render_system_template(
                title_template, locale, template_vars, translate_vars,
            )[:255]
        if body_template:
            body = _render_system_template(
                body_template, locale, template_vars, translate_vars,
            )

    # Санитизируем ДО создания строки — покрывает in-app + e-mail forward (ниже) +
    # TG forward (читает n.link_url). broadcast() идёт через notify() → тоже покрыт.
    link_url = _safe_link_url(link_url)

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
    # Буферим WS-пуш ДО собственного commit — отправит after_commit-листенер
    # (для commit=False — на коммите роута/get_db). Никогда не шлём до коммита.
    _buffer_ws_push(db, recipient_id, n)

    if commit:
        await db.commit()
        if not in_app_only:
            # Telegram-канал удалён (решение владельца 05.08.2026) — остаются
            # in-app и e-mail.
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

    # WS-пуш выполнит after_commit-листенер из session.info (см. _buffer_ws_push).
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
