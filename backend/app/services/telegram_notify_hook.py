"""Forward platform notifications into the Telegram outbox (Pack 13.2).

Called by notifications_service + admin_broadcast_service after Notification commit.
Never raises — failures only get logged.
"""
import logging
from datetime import datetime
from typing import Optional

from app.config import settings
from app.models.notification import Notification
from app.models.user import User
from app.services import tg_banner

log = logging.getLogger(__name__)


PRIORITY_MARKERS = {
    "critical": "[КРИТИЧНО]",
    "high":     "[ВАЖНО]",
    "normal":   "[Уведомление]",
    "low":      "[Уведомление]",
}

# Phase A: type-prefix → enabled module-specific approve/reject buttons
_DECISION_MODULE_PREFIXES = ("kpi.", "procurement.", "bp.", "credit.", "loan.")


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


def _module_from_type(n_type: str) -> str:
    """Derive banner module key from a notification type."""
    t = (n_type or "").lower()
    if t.startswith("moderation"): return "moderation"
    if t.startswith("kpi"):        return "kpi"
    if t.startswith("bp"):         return "bp"
    if t.startswith("procurement"):return "procurement"
    if t.startswith("credit") or t.startswith("loan"): return "credit"
    if t.startswith("deadline"):   return "deadline"
    if t in ("mention", "comment.replied", "assignment"): return "tasks"
    if t.startswith("rbac") or t.startswith("auth"): return "auth"
    if t.startswith("audit"):      return "audit"
    return "system"


def _severity_from_priority(priority: str, n_type: str = "") -> str:
    """Map notification priority to banner severity bucket."""
    p = (priority or "normal").lower()
    if p == "critical": return "critical"
    if p == "high":     return "warning"
    # success cluster — approved / achieved events
    t = (n_type or "").lower()
    if t.endswith(".approved") or t.endswith(".achieved") or t.endswith(".done"):
        return "success"
    return "info"


def _build_payload(notif: Notification, source_user: Optional[User]) -> dict:
    """Phase A+B: shape consumed by bot/formatter._fmt_notification.
    Adds parse_mode=HTML, module/severity hints, and a banner photo URL.
    Pack 149: enriched mention payload includes company / entity title / comment text.
    """
    subject = None
    meta: dict = {}
    # Notification.payload (JSONB) carries custom fields set by callers
    raw_payload = getattr(notif, "payload", None) or {}
    if isinstance(raw_payload, dict):
        meta = raw_payload
        # For mention / comment.replied: build subject from entity title + company
        if notif.type in ("mention", "comment.replied"):
            et = meta.get("entity_title", "")
            cn = meta.get("company_name", "")
            if et and cn:
                subject = f"{et} · {cn}"
            elif et:
                subject = et
            elif cn:
                subject = cn
        if subject is None:
            subject = meta.get("subject") or meta.get("company_label")

    n_type = notif.type or ""
    module = _module_from_type(n_type)
    severity = _severity_from_priority(notif.priority or "normal", n_type)

    # Banner URL — Telegram fetches this from the public platform URL
    platform_base = (getattr(settings, "PLATFORM_URL", None) or "https://localhost").rstrip("/")
    # Phase B v3: optional headline_metric (big focal number on banner).
    # Callers pass it via Notification.payload["headline_metric"] — e.g.
    # KPI alert: "85%", credit overdue: "$12.4M", deadline: "7 дней".
    headline_metric = None
    try:
        np = getattr(notif, "payload", None) or {}
        if isinstance(np, dict):
            headline_metric = np.get("headline_metric")
            if headline_metric is not None:
                headline_metric = str(headline_metric)[:32]
    except Exception:
        headline_metric = None
    banner_url = tg_banner.get_banner_url(
        platform_base, module, severity, headline_metric=headline_metric,
    )

    # Actor name: prefer payload[actor_name] (set by mention_service), then
    # source_user, then None.
    actor_str = (
        (meta.get("actor_name") if isinstance(meta, dict) else None)
        or (source_user.full_name or source_user.email if source_user else None)
    )

    return {
        "parse_mode": "HTML",
        "marker":     PRIORITY_MARKERS.get(notif.priority or "normal", "[Уведомление]"),
        "title":      notif.title or "",
        "body":       notif.body or "",
        "subject":    subject,
        "deep_link":  _platform_link(notif),
        "actor":      actor_str,
        "when":       _fmt_when(notif.created_at),
        "version":    (meta.get("version") if isinstance(meta, dict) else None),
        # Mention-specific extras (used by bot to build the Reply button)
        "comment_id":   meta.get("comment_id") if isinstance(meta, dict) else None,
        "entity_id":    meta.get("entity_id") if isinstance(meta, dict) else None,
        "entity_type":  meta.get("entity_type") if isinstance(meta, dict) else None,
        # Phase B — photo banner
        "banner":     True,
        "banner_url": banner_url,
        "banner_module":   module,
        "banner_severity": severity,
        "banner_headline": headline_metric,
        # Extras for callback handling
        "notif_id":   str(notif.id),
        "n_type":     n_type,
        "n_priority": notif.priority,
    }


def _twa_link(path: str) -> str:
    """Build a Telegram Mini App deep-link to a /twa/* route."""
    base = (getattr(settings, "PLATFORM_URL", None) or "https://localhost").rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}/twa{path}"


def _build_inline_buttons(notif: Notification) -> Optional[list]:
    """Inline keyboard layout. Phase A added module-specific approve/reject
    quick actions; Phase C adds a third row pointing at the Telegram Mini App
    so the user can review the same item with full visual context."""
    link = _platform_link(notif)
    n_type = (notif.type or "").lower()
    src_id = notif.source_entity_id

    def _twa_button_for(module: str) -> dict | None:
        """Build the «📱 В Mini App» button when we have a TWA route for it."""
        if not src_id:
            return None
        if module == "procurement":
            return {"text": "📱 Открыть в Mini App", "url": _twa_link(f"/procurement/{src_id}")}
        return {"text": "📱 Открыть в Mini App", "url": _twa_link(f"/approve/{src_id}")}

    # 1) Generic moderation queue (KPI/BP/governance/etc bundled together)
    if n_type == "moderation.pending" and src_id:
        rows: list[list[dict]] = [
            [
                {"text": "✓ Принять",   "callback_data": f"mod:approve:{src_id}"},
                {"text": "✗ Отклонить", "callback_data": f"mod:reject:{src_id}"},
            ],
            [{"text": "Открыть в платформе →", "url": link}],
        ]
        twa_btn = _twa_button_for("generic")
        if twa_btn:
            rows.append([twa_btn])
        return rows

    # 2) Module-specific approval prompts (sent directly, not via moderation)
    if src_id:
        if n_type.startswith("kpi.") and "approval" in n_type:
            rows = [
                [
                    {"text": "✓ Утвердить",    "callback_data": f"kpi_approve:{src_id}"},
                    {"text": "✗ На доработку", "callback_data": f"kpi_reject:{src_id}"},
                ],
                [{"text": "Открыть в платформе →", "url": link}],
            ]
            twa_btn = _twa_button_for("kpi")
            if twa_btn:
                rows.append([twa_btn])
            return rows
        if n_type.startswith("procurement.") and ("approval" in n_type or "review" in n_type):
            rows = [
                [
                    {"text": "✓ Одобрить",  "callback_data": f"procurement_approve:{src_id}"},
                    {"text": "✗ Отклонить", "callback_data": f"procurement_reject:{src_id}"},
                ],
                [{"text": "Открыть в платформе →", "url": link}],
            ]
            twa_btn = _twa_button_for("procurement")
            if twa_btn:
                rows.append([twa_btn])
            return rows

    # Mention + comment.replied: open + reply-in-bot
    # Both share the same "reply to entity" UX — clicking «Ответить в чате»
    # opens a pending-reply state in the bot for the same task/project.
    if n_type in ("mention", "comment.replied") and src_id:
        np = notif.payload if isinstance(notif.payload, dict) else {}
        ent_type = np.get("entity_type", "task")
        rows = [
            [{"text": "💬 Ответить в чате", "callback_data": f"mention_reply:{ent_type}:{src_id}"}],
            [{"text": "Открыть в платформе →", "url": link}],
        ]
        return rows

    # 3) Fallback — just a deep-link
    return [
        [{"text": "Открыть в платформе →", "url": link}],
    ]
