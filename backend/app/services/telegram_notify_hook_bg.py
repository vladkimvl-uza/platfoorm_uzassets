"""Fire-and-forget Telegram forwarder (Pack 13.2.3).

Public API:
    schedule_forward(notif_id: str) -> None

The function returns instantly; the actual DB work + outbox insert happen
in an asyncio task with its OWN session. This way any failure cannot
propagate back into the request handler that triggered the notification.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.mfa import OutboxType, TelegramOutbox, UserTelegramPref
from app.models.notification import Notification
from app.models.user import User
from app.services import mfa_service

log = logging.getLogger(__name__)


TYPE_TO_PREF_FIELD: dict[str, str] = {
    "moderation.pending":          "type_moderation",
    "moderation.approved":         "type_moderation",
    "moderation.rejected":         "type_moderation",
    "moderation.review_requested": "type_moderation",
    "moderation.escalated":        "type_moderation",
    "moderation.expired":          "type_moderation",
    "mention":         "type_mentions",
    "assignment":      "type_assignments",
    "comment.replied": "type_mentions",
    "deadline.approaching": "type_deadlines",
    "deadline.missed":      "type_deadlines",
    "kpi.target.missed":   "type_system",
    "kpi.achieved":        "type_system",
    "audit.security_flag": "type_system",
    "rbac.changed":        "type_system",
    "system.announcement": "type_system",
    "data.imported":       "type_system",
    "report.ready":        "type_system",
}

PRIORITY_MARKERS = {
    "critical": "[КРИТИЧНО]",
    "high":     "[ВАЖНО]",
    "normal":   "[Уведомление]",
    "low":      "[Уведомление]",
}


def _platform_link(notif: Notification) -> str:
    from app.config import settings
    base = (getattr(settings, "PLATFORM_URL", None) or "https://localhost").rstrip("/")
    if notif.link_url:
        return notif.link_url if notif.link_url.startswith("http") else f"{base}{notif.link_url}"
    return f"{base}/notifications"


def _build_payload(notif: Notification, source_user: Optional[User]) -> dict:
    when = None
    if notif.created_at:
        try:
            when = notif.created_at.strftime("%d.%m %H:%M")
        except Exception:
            pass
    return {
        "marker":    PRIORITY_MARKERS.get(notif.priority or "normal", "[Уведомление]"),
        "title":     notif.title or "",
        "body":      notif.body or "",
        "deep_link": _platform_link(notif),
        "actor":     (source_user.full_name or source_user.email) if source_user else None,
        "when":      when,
        "notif_id":  str(notif.id),
        "n_type":    notif.type,
    }


def _build_buttons(notif: Notification) -> Optional[list]:
    link = _platform_link(notif)
    if notif.type == "moderation.pending" and notif.source_entity_id:
        return [
            [{"text": "Открыть", "url": link}],
            [
                {"text": "Принять",   "callback_data": f"mod:approve:{notif.source_entity_id}"},
                {"text": "Отклонить", "callback_data": f"mod:reject:{notif.source_entity_id}"},
            ],
        ]
    return [[{"text": "Открыть в платформе", "url": link}]]


async def _do_forward(notif_id: str) -> None:
    """Runs in a separate task with its own session."""
    try:
        async with AsyncSessionLocal() as db:
            notif = await db.get(Notification, notif_id)
            if notif is None:
                return
            user = await db.get(User, notif.recipient_user_id)
            if user is None or not getattr(user, "telegram_chat_id_encrypted", None):
                return

            pref: UserTelegramPref = await mfa_service.get_or_create_pref(db, str(user.id))
            severity = notif.priority or "normal"
            if not mfa_service.should_route_to_telegram(
                pref=pref, notification_type=notif.type, severity=severity,
            ):
                return

            source_user = None
            if notif.source_user_id:
                source_user = await db.get(User, notif.source_user_id)

            ob = TelegramOutbox(
                created_at=datetime.now(timezone.utc),
                user_id=user.id,
                type=OutboxType.NOTIFICATION,
                payload=_build_payload(notif, source_user),
                inline_buttons=_build_buttons(notif),
            )
            db.add(ob)
            await db.commit()
            log.info(
                "tg-forward(bg): notif=%s type=%s priority=%s -> outbox=%s user=%s",
                notif.id, notif.type, notif.priority, ob.id, user.email,
            )
    except Exception as e:
        log.warning("tg-forward(bg) failed for notif=%s: %s", notif_id, e, exc_info=True)


def schedule_forward(notif_id: str) -> None:
    """Schedule forwarding as a fire-and-forget task. Returns immediately."""
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_do_forward(notif_id))
        # Ignore the task — it will run on its own. Add a done-callback
        # only to surface unexpected exceptions.
        task.add_done_callback(_log_done)
    except RuntimeError:
        # No event loop — must be sync context; drop.
        pass


def _log_done(t: asyncio.Task) -> None:
    if t.cancelled():
        return
    exc = t.exception()
    if exc:
        log.warning("tg-forward(bg) task ended with exception: %s", exc)