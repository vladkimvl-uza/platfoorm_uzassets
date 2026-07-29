"""Format outbox payloads into Telegram HTML message text (Phase A: premium upgrade).

All renderers produce HTML — main.py sets DefaultBotProperties(parse_mode=HTML).
Telegram-supported tags only: <b> <i> <u> <s> <code> <pre> <blockquote> <a> <tg-spoiler> <br/>.
"""
from html import escape as _esc
from typing import Optional

import config
from i18n import msg, normalize_locale


# ── Dispatch ─────────────────────────────────────────────────────────────

def format_outbox(msg_type: str, payload: dict, email: str) -> str:
    """Dispatch on message type → render HTML body."""
    handlers = {
        "mfa_code":          _fmt_mfa_code,
        "link_confirmation": _fmt_link_confirmation,
        "notification":      _fmt_notification,
        "test":              _fmt_test,
    }
    h = handlers.get(msg_type, _fmt_unknown)
    return h(payload, email, normalize_locale(payload.get("locale")))


# ── Specific renderers ───────────────────────────────────────────────────

def _fmt_mfa_code(p: dict, email: str, locale: str = "ru") -> str:
    code = str(p.get("code", "?"))
    pretty = code[:3] + " " + code[3:] if len(code) == 6 else code
    ttl = p.get("ttl_minutes", 5)
    ip = p.get("ip") or "—"
    geo = p.get("geo") or ""
    when = p.get("when") or ""
    purpose = (p.get("purpose") or "").lower()

    if purpose == "password_reset":
        # Восстановление пароля — отдельный шаблон, без IP/гео блока
        # (запрос не привязан к свежей сессии браузера).
        parts = [
            f"<b>UzAssets · {msg('password_recovery', locale)}</b>",
            "",
            f"<blockquote><code>{_esc(pretty)}</code></blockquote>",
            msg("code_valid_minutes", locale, minutes=int(ttl)),
            "",
            f"{msg('account', locale)}: <code>{_esc(email)}</code>",
            "",
            f"<i>{msg('password_reset_warning', locale)}</i>",
        ]
        return "\n".join(parts)

    parts = [
        f"<b>UzAssets · {msg('access_code', locale)}</b>",
        "",
        f"<blockquote><code>{_esc(pretty)}</code></blockquote>",
        msg("valid_minutes", locale, minutes=int(ttl)),
        "",
        f"{msg('account', locale)}: <code>{_esc(email)}</code>",
    ]
    ip_line = f"IP: <code>{_esc(str(ip))}</code>"
    if geo:
        ip_line += f" · {_esc(str(geo))}"
    parts.append(ip_line)
    if when:
        parts.append(_esc(str(when)))
    parts.extend([
        "",
        f"<i>{msg('login_warning', locale)}</i>",
    ])
    return "\n".join(parts)


def _fmt_link_confirmation(p: dict, email: str, locale: str = "ru") -> str:
    url = f"{config.PLATFORM_URL}/settings/security"
    return (
        f"<b>UzAssets · {msg('link_success', locale)}</b>\n"
        "\n"
        + msg("link_confirmation_body", locale, email=_esc(email), url=_esc(url))
    )


def _fmt_notification(p: dict, email: str, locale: str = "ru") -> str:
    """Generic notification with rich HTML. Module-aware header + blockquote subject."""
    n_type    = p.get("n_type") or ""
    priority  = (p.get("n_priority") or "normal").lower()
    title     = str(p.get("title") or msg("notification", locale))
    body      = str(p.get("body") or "")
    deep_link = p.get("deep_link")
    actor     = p.get("actor")
    when      = p.get("when")
    subject   = p.get("subject")  # e.g. KPI 2026 · АО "Навоийский ГМК"

    header = _build_module_header(n_type, priority, locale)
    parts: list[str] = [f"<b>{_esc(header)}</b>", ""]

    if subject:
        parts.extend([f"<blockquote>{_esc(str(subject))}</blockquote>", ""])
    elif title:
        parts.extend([f"<blockquote>{_esc(title)}</blockquote>", ""])

    if body:
        parts.append(_esc(body))

    meta: list[str] = []
    if actor: meta.append(f"{msg('author', locale)}: <b>{_esc(str(actor))}</b>")
    if when:  meta.append(f"{msg('when', locale)}: {_esc(str(when))}")
    version = p.get("version")
    if version: meta.append(f"{msg('version', locale)}: <code>{_esc(str(version))}</code>")

    if meta:
        parts.append("")
        parts.extend(meta)

    if priority == "critical":
        parts.append("")
        parts.append(f"<i>{msg('automatic_monitoring', locale)}</i>")

    # Deep-link rendered as inline button (see _build_inline_buttons in backend),
    # but keep a textual fallback for clients without buttons.
    if deep_link and not _has_button_for(deep_link, p):
        parts.append("")
        parts.append(f"<a href=\"{_esc(str(deep_link))}\">{msg('open_platform', locale)}</a>")

    return "\n".join(parts)


def _fmt_test(p: dict, email: str, locale: str = "ru") -> str:
    title = str(p.get("title") or msg("test_notification", locale))
    body  = str(p.get("body")  or msg("telegram_ok", locale))
    return (
        f"<b>UzAssets · {msg('test', locale)}</b>\n"
        "\n"
        f"<blockquote>{_esc(title)}</blockquote>\n"
        "\n"
        f"{_esc(body)}\n"
        "\n"
        f"{msg('account', locale)}: <code>{_esc(email)}</code>"
    )


def _fmt_unknown(p: dict, email: str, locale: str = "ru") -> str:
    return (
        "<b>UzAssets</b>\n"
        "\n"
        f"<pre>{_esc(str(p))}</pre>\n"
        "\n"
        f"{msg('account', locale)}: <code>{_esc(email)}</code>"
    )


# ── Helpers ──────────────────────────────────────────────────────────────

def _build_module_header(n_type: str, priority: str, locale: str = "ru") -> str:
    """Translate notification-type+priority into a one-line header."""
    sev_map = {
        "critical": msg("critical", locale),
        "high":     msg("important", locale),
    }
    sev = sev_map.get(priority, "")
    n_type = (n_type or "").lower()

    if n_type.startswith("moderation"):
        module = msg("module_moderation", locale)
    elif n_type.startswith("kpi"):
        module = "KPI"
    elif n_type.startswith("bp"):
        module = msg("module_bp", locale)
    elif n_type.startswith("procurement"):
        module = msg("module_procurement", locale)
    elif n_type.startswith("credit") or n_type.startswith("loan"):
        module = msg("module_credit", locale)
    elif n_type.startswith("deadline"):
        module = msg("module_deadline", locale)
    elif n_type in ("mention", "comment.replied"):
        module = msg("module_mention", locale)
    elif n_type == "assignment":
        module = msg("module_assignment", locale)
    elif n_type.startswith("rbac"):
        module = msg("module_access", locale)
    elif n_type.startswith("audit"):
        module = msg("module_audit", locale)
    elif n_type.startswith("system") or n_type.startswith("data") or n_type.startswith("report"):
        module = msg("module_system", locale)
    else:
        module = msg("notification", locale)

    parts = ["UzAssets", module]
    if sev:
        parts.insert(1, sev)
    return " · ".join(parts)


def _has_button_for(link: str, payload: dict) -> bool:
    """Return True if the inline-buttons payload already contains a URL-button
    for that link (so we don't duplicate it inside the message text)."""
    btns = payload.get("inline_buttons") or []
    if not isinstance(btns, list):
        return False
    for row in btns:
        if isinstance(row, dict):
            row = [row]
        if not isinstance(row, list):
            continue
        for b in row:
            if isinstance(b, dict) and b.get("url") == link:
                return True
    return False


# ── Command response helpers ─────────────────────────────────────────────

def fmt_help(locale: str = "ru") -> str:
    return msg("help", locale, url=_esc(config.PLATFORM_URL))


def fmt_welcome_no_token(locale: str = "ru") -> str:
    url = f"{config.PLATFORM_URL}/settings/security"
    return msg("welcome", locale, url=_esc(url))


def fmt_link_success(email: str, full_name: str = "", locale: str = "ru") -> str:
    salutation = _esc(full_name) if full_name else _esc(email)
    url = f"{config.PLATFORM_URL}/settings/notifications"
    return msg("link_ready", locale, name=salutation, url=_esc(url))


def fmt_menu(locale: str = "ru") -> str:
    return msg("menu", locale)


def fmt_status(user_email: str, notifications: list[dict], locale: str = "ru") -> str:
    if not notifications:
        return (
            f"<b>UzAssets · {_esc(user_email)}</b>\n"
            "\n"
            + msg("no_unread", locale)
        )
    lines = [
        f"<b>UzAssets · {_esc(user_email)}</b>",
        msg("unread_count", locale, count=len(notifications)),
        "",
    ]
    for n in notifications[:5]:
        title = n.get("title") or n.get("type") or msg("untitled", locale)
        when = n.get("created_at")
        when_str = when.strftime("%d.%m %H:%M") if hasattr(when, "strftime") else str(when)
        lines.append(f"· <b>{_esc(str(title))}</b>")
        lines.append(f"  <i>{_esc(when_str)}</i>")
    return "\n".join(lines)


def fmt_queue(items: list[dict], locale: str = "ru") -> str:
    if not items:
        return msg("queue_empty", locale)
    lines = [
        msg("queue_header", locale),
        msg("queue_count", locale, count=len(items)),
        "",
    ]
    for it in items[:10]:
        module = it.get("module", "?")
        submitter = it.get("submitter_email") or "?"
        when = it.get("created_at")
        when_str = when.strftime("%d.%m %H:%M") if hasattr(when, "strftime") else str(when)
        lines.append(msg(
            "queue_from", locale,
            module=_esc(str(module)), submitter=_esc(str(submitter)),
        ))
        lines.append(f"  <i>{_esc(when_str)}</i>")
    lines.append("")
    lines.append(
        f"<a href=\"{_esc(config.PLATFORM_URL)}/admin/moderation\">{msg('open_queue', locale)}</a>"
    )
    return "\n".join(lines)


def fmt_sessions(sessions: list[dict], locale: str = "ru") -> str:
    if not sessions:
        return msg("sessions_empty", locale)
    lines = [
        msg("sessions_header", locale),
        msg("total", locale, count=len(sessions)),
        "",
    ]
    for s in sessions:
        last = s.get("last_seen_at") or s.get("created_at")
        last_str = last.strftime("%d.%m %H:%M") if hasattr(last, "strftime") else str(last)
        ip = s.get("ip_address") or "—"
        ua = (s.get("user_agent") or "")[:50]
        lines.append(f"· <b>{_esc(last_str)}</b> · <code>{_esc(str(ip))}</code>")
        if ua:
            lines.append(f"  <i>{_esc(ua)}</i>")
    return "\n".join(lines)


def fmt_unlinked(locale: str = "ru") -> str:
    url = f"{config.PLATFORM_URL}/settings/security"
    return msg("unlinked", locale, url=_esc(url))


def fmt_not_linked(locale: str = "ru") -> str:
    url = f"{config.PLATFORM_URL}/settings/security"
    return msg("not_linked", locale, url=_esc(url))


def fmt_link_token_invalid(locale: str = "ru") -> str:
    url = f"{config.PLATFORM_URL}/settings/security"
    return msg("invalid_token", locale, url=_esc(url))


# ── Inline-keyboard builders ─────────────────────────────────────────────

def build_buttons_for_mfa(
    mfa_token: Optional[str] = None, locale: str = "ru",
) -> list:
    """Inline buttons for MFA messages. mfa_token is the short-lived ID we use
    to identify the attempt for «Это не я» reporting."""
    suffix = (mfa_token or "")[:64]
    return [
        [
            {"text": msg("not_me", locale), "callback_data": f"mfa_not_me:{suffix}"},
        ],
    ]


def build_buttons_for_kpi_review(
    submission_id: str, deep_link: Optional[str] = None, locale: str = "ru",
) -> list:
    rows = [
        [
            {"text": f"✓ {msg('approve', locale)}",    "callback_data": f"kpi_approve:{submission_id}"},
            {"text": f"✗ {msg('request_changes', locale)}", "callback_data": f"kpi_reject:{submission_id}"},
        ],
    ]
    if deep_link:
        rows.append([{"text": msg("open_platform", locale), "url": deep_link}])
    return rows


def build_buttons_for_procurement_review(
    submission_id: str, deep_link: Optional[str] = None, locale: str = "ru",
) -> list:
    rows = [
        [
            {"text": f"✓ {msg('accept', locale)}",  "callback_data": f"procurement_approve:{submission_id}"},
            {"text": f"✗ {msg('reject', locale)}", "callback_data": f"procurement_reject:{submission_id}"},
        ],
    ]
    if deep_link:
        rows.append([{"text": msg("open_platform", locale), "url": deep_link}])
    return rows
