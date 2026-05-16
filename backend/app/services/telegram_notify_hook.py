"""Forward platform notifications into the Telegram outbox (Pack 13.2).

Called by notifications_service + admin_broadcast_service after Notification commit.
Never raises — failures only get logged.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.mfa import OutboxType, TelegramOutbox, UserTelegramPref
from app.models.notification import Notification
from app.models.user import User
from app.services import mfa_service

log = logging.getLogger(__name__)


# Map Notification.type → pref field on UserTelegramPref
TYPE_TO_PREF_FIELD: dict[str, str] = {
    # Moderation cluster
    "moderation.pending":          "type_moderation",
    "moderation.approved":         "type_moderation",
    "moderation.rejected":         "type_moderation",
    "moderation.review_requested": "type_moderation",
    "moderation.escalated":        "type_moderation",
    "moderation.expired":          "type_moderation",
    # Interactions
    "mention":         "type_mentions",
    "assignment":      "type_assignments",
    "comment.replied": "type_mentions",
    # Deadlines
    "deadline.approaching": "type_deadlines",
    "deadline.missed":      "type_deadlines",
    # KPI / audit / RBAC
    "kpi.target.missed":   "type_system",
    "kpi.achieved":        "type_system",
    "audit.security_flag": "type_system",
    "rbac.changed":        "type_system",
    # System
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
    base = (getattr(settings, "PLATFORM_URL", None) or "https://localhost").rstrip("/")
    if notif.link_url:
        return notif.link_url if notif.link_url.startswith("http") else f"{base}{notif.link_url}"
    return f"{base}/notifications"


def _fmt_when(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    try:
        return dt.strftime("%d.%m %H:%M")
    except Exception:
        return None


def _build_payload(notif: Notification, source_user: Optional[User]) -> dict:
    """Match the shape expected by bot/formatter._fmt_notification:
       marker, title, body, deep_link, actor, when"""
    return {
        "marker":    PRIORITY_MARKERS.get(notif.priority or "normal", "[Уведомление]"),
        "title":     notif.title or "",
        "body":      notif.body or "",
        "deep_link": _platform_link(notif),
        "actor":     (source_user.full_name or source_user.email) if source_user else None,
        "when":      _fmt_when(notif.created_at),
        # Extras for callback handling
        "notif_id":  str(notif.id),
        "n_type":   notif.type,
        "n_priority": notif.priority,
    }


def _build_inline_buttons(notif: Notification) -> Optional[list]:
    """Inline keyboard. For pending moderation, also Approve/Reject callback buttons."""
    link = _platform_link(notif)
    if notif.type == "moderation.pending" and notif.source_entity_id:
        return [
            [{"text": "Открыть", "url": link}],
            [
                {"text": "Принять",   "callback_data": f"mod:approve:{notif.source_entity_id}"},
                {"text": "Отклонить", "callback_data": f"mod:reject:{notif.source_entity_id}"},
            ],
        ]
    return [
        [{"text": "Открыть в платформе", "url": link}],
    ]


async def forward_notification_to_telegram(
    db: AsyncSession,
    notif: Notification,
) -> bool:
    """Enqueue notification into telegram_outbox if user prefs allow.

    Returns True if enqueued, False otherwise. Never raises.
    """
    try:
        user = await db.get(User, notif.recipient_user_id)
        if user is None:
            return False
        if not getattr(user, "telegram_chat_id_encrypted", None):
            return False

        pref: UserTelegramPref = await mfa_service.get_or_create_pref(db, str(user.id))

        pref_field = TYPE_TO_PREF_FIELD.get(notif.type, "type_system")
        severity = notif.priority or "normal"

        routed = mfa_service.should_route_to_telegram(
            pref=pref, pref_field=pref_field, severity=severity,
        )
        if not routed:
            return False

        source_user = None
        if notif.source_user_id:
            source_user = await db.get(User, notif.source_user_id)

        ob = TelegramOutbox(
            user_id=user.id,
            type=OutboxType.NOTIFICATION,
            payload=_build_payload(notif, source_user),
            inline_buttons=_build_inline_buttons(notif),
        )
        db.add(ob)
        await db.commit()

        log.info(
            "tg-forward: notif=%s type=%s priority=%s -> outbox=%s user=%s",
            notif.id, notif.type, notif.priority, ob.id, user.email,
        )
        return True

    except Exception as e:
        log.warning(
            "tg-forward failed for notif=%s type=%s: %s",
            getattr(notif, "id", "?"), getattr(notif, "type", "?"), e,
            exc_info=True,
        )
        try:
            await db.rollback()
        except Exception:
            pass
        return False
