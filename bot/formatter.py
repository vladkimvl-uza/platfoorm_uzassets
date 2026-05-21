"""Format outbox payloads into Telegram HTML message text (Phase A: premium upgrade).

All renderers produce HTML — main.py sets DefaultBotProperties(parse_mode=HTML).
Telegram-supported tags only: <b> <i> <u> <s> <code> <pre> <blockquote> <a> <tg-spoiler> <br/>.
"""
from html import escape as _esc
from typing import Optional

import config


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
    return h(payload, email)


# ── Specific renderers ───────────────────────────────────────────────────

def _fmt_mfa_code(p: dict, email: str) -> str:
    code = str(p.get("code", "?"))
    pretty = code[:3] + " " + code[3:] if len(code) == 6 else code
    ttl = p.get("ttl_minutes", 5)
    ip = p.get("ip") or "—"
    geo = p.get("geo") or ""
    when = p.get("when") or ""
    parts = [
        "<b>UzAssets · Код доступа</b>",
        "",
        f"<blockquote><code>{_esc(pretty)}</code></blockquote>",
        f"Действителен <b>{int(ttl)} минут</b>",
        "",
        f"Аккаунт: <code>{_esc(email)}</code>",
    ]
    ip_line = f"IP: <code>{_esc(str(ip))}</code>"
    if geo:
        ip_line += f" · {_esc(str(geo))}"
    parts.append(ip_line)
    if when:
        parts.append(_esc(str(when)))
    parts.extend([
        "",
        "<i>Если это были не вы — нажмите «Это не я».</i>",
    ])
    return "\n".join(parts)


def _fmt_link_confirmation(p: dict, email: str) -> str:
    return (
        "<b>UzAssets · Привязка успешна</b>\n"
        "\n"
        f"Аккаунт <code>{_esc(email)}</code> связан с этим чатом.\n"
        "\n"
        "Теперь при входе вам будет приходить <b>код доступа</b>. "
        "Дублирование уведомлений (задачи, дедлайны, модерация) — в настройках:\n"
        f"<a href=\"{_esc(config.PLATFORM_URL)}/settings/security\">{_esc(config.PLATFORM_URL)}/settings/security</a>"
    )


def _fmt_notification(p: dict, email: str) -> str:
    """Generic notification with rich HTML. Module-aware header + blockquote subject."""
    n_type    = p.get("n_type") or ""
    priority  = (p.get("n_priority") or "normal").lower()
    title     = str(p.get("title") or "Уведомление")
    body      = str(p.get("body") or "")
    deep_link = p.get("deep_link")
    actor     = p.get("actor")
    when      = p.get("when")
    subject   = p.get("subject")  # e.g. KPI 2026 · АО "Навоийский ГМК"

    header = _build_module_header(n_type, priority)
    parts: list[str] = [f"<b>{_esc(header)}</b>", ""]

    if subject:
        parts.extend([f"<blockquote>{_esc(str(subject))}</blockquote>", ""])
    elif title:
        parts.extend([f"<blockquote>{_esc(title)}</blockquote>", ""])

    if body:
        parts.append(_esc(body))

    meta: list[str] = []
    if actor: meta.append(f"Автор: <b>{_esc(str(actor))}</b>")
    if when:  meta.append(f"Когда: {_esc(str(when))}")
    version = p.get("version")
    if version: meta.append(f"Версия: <code>{_esc(str(version))}</code>")

    if meta:
        parts.append("")
        parts.extend(meta)

    if priority == "critical":
        parts.append("")
        parts.append("<i>Автоматический мониторинг.</i>")

    # Deep-link rendered as inline button (see _build_inline_buttons in backend),
    # but keep a textual fallback for clients without buttons.
    if deep_link and not _has_button_for(deep_link, p):
        parts.append("")
        parts.append(f"<a href=\"{_esc(str(deep_link))}\">Открыть в платформе →</a>")

    return "\n".join(parts)


def _fmt_test(p: dict, email: str) -> str:
    title = str(p.get("title") or "Тестовое уведомление UzAssets")
    body  = str(p.get("body")  or "Доставка через Telegram работает корректно.")
    return (
        "<b>UzAssets · Тест</b>\n"
        "\n"
        f"<blockquote>{_esc(title)}</blockquote>\n"
        "\n"
        f"{_esc(body)}\n"
        "\n"
        f"Аккаунт: <code>{_esc(email)}</code>"
    )


def _fmt_unknown(p: dict, email: str) -> str:
    return (
        "<b>UzAssets</b>\n"
        "\n"
        f"<pre>{_esc(str(p))}</pre>\n"
        "\n"
        f"Аккаунт: <code>{_esc(email)}</code>"
    )


# ── Helpers ──────────────────────────────────────────────────────────────

def _build_module_header(n_type: str, priority: str) -> str:
    """Translate notification-type+priority into a one-line header."""
    sev_map = {
        "critical": "CRITICAL",
        "high":     "Важно",
    }
    sev = sev_map.get(priority, "")
    n_type = (n_type or "").lower()

    if n_type.startswith("moderation"):
        module = "Модерация"
    elif n_type.startswith("kpi"):
        module = "KPI"
    elif n_type.startswith("bp"):
        module = "Бизнес-план"
    elif n_type.startswith("procurement"):
        module = "Закупки"
    elif n_type.startswith("credit") or n_type.startswith("loan"):
        module = "Кредит"
    elif n_type.startswith("deadline"):
        module = "Дедлайн"
    elif n_type in ("mention", "comment.replied"):
        module = "Упоминание"
    elif n_type == "assignment":
        module = "Назначение"
    elif n_type.startswith("rbac"):
        module = "Доступ"
    elif n_type.startswith("audit"):
        module = "Аудит"
    elif n_type.startswith("system") or n_type.startswith("data") or n_type.startswith("report"):
        module = "Система"
    else:
        module = "Уведомление"

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

def fmt_help() -> str:
    return (
        "<b>UzAssets · Справка</b>\n"
        "\n"
        "<b>Команды:</b>\n"
        "/start <i>&lt;токен&gt;</i> — привязать аккаунт\n"
        "/menu — главное меню\n"
        "/status — мои последние уведомления\n"
        "/queue — модерация (для модераторов)\n"
        "/sessions — мои активные сессии\n"
        "/unlink — отвязать Telegram\n"
        "/help — эта справка\n"
        "\n"
        f"Платформа: <a href=\"{_esc(config.PLATFORM_URL)}\">{_esc(config.PLATFORM_URL)}</a>\n"
        "Поддержка: <code>v.kim@uz-assets.uz</code>"
    )


def fmt_welcome_no_token() -> str:
    return (
        "<b>UzAssets · Bot</b>\n"
        "\n"
        "Здравствуйте. Чтобы связать аккаунт с этим чатом:\n"
        "\n"
        "1. Откройте платформу UzAssets\n"
        "2. <b>Настройки → Безопасность → Связать Telegram</b>\n"
        "3. Нажмите кнопку с QR-кодом или скопируйте ссылку\n"
        "\n"
        "Затем эта ссылка приведёт вас обратно сюда с токеном привязки.\n"
        "\n"
        f"<a href=\"{_esc(config.PLATFORM_URL)}/settings/security\">{_esc(config.PLATFORM_URL)}/settings/security</a>\n"
        "\n"
        "Список команд: /help"
    )


def fmt_link_success(email: str, full_name: str = "") -> str:
    salutation = _esc(full_name) if full_name else _esc(email)
    return (
        "<b>UzAssets · Bot готов к работе</b>\n"
        "\n"
        f"Привязка успешна, <b>{salutation}</b>.\n"
        "\n"
        "<b>Что я могу:</b>\n"
        "— Отправлять <b>коды доступа</b> при входе на платформу\n"
        "— Уведомлять о <b>задачах</b> и <b>дедлайнах</b>\n"
        "— Сообщать о <b>модерации</b> закупок и BP\n"
        "— Алерты по <b>кредитному портфелю</b>\n"
        "\n"
        "Настройка уведомлений:\n"
        f"<a href=\"{_esc(config.PLATFORM_URL)}/settings/notifications\">"
        f"{_esc(config.PLATFORM_URL)}/settings/notifications</a>"
    )


def fmt_menu() -> str:
    return (
        "<b>UzAssets · Меню</b>\n"
        "\n"
        "Выберите раздел внизу экрана или используйте команды:\n"
        "/status — уведомления\n"
        "/queue — модерация\n"
        "/sessions — активные сессии\n"
        "/help — справка"
    )


def fmt_status(user_email: str, notifications: list[dict]) -> str:
    if not notifications:
        return (
            f"<b>UzAssets · {_esc(user_email)}</b>\n"
            "\n"
            "Непрочитанных уведомлений нет."
        )
    lines = [
        f"<b>UzAssets · {_esc(user_email)}</b>",
        f"Непрочитанных: <b>{len(notifications)}</b>",
        "",
    ]
    for n in notifications[:5]:
        title = n.get("title") or n.get("type") or "(без заголовка)"
        when = n.get("created_at")
        when_str = when.strftime("%d.%m %H:%M") if hasattr(when, "strftime") else str(when)
        lines.append(f"· <b>{_esc(str(title))}</b>")
        lines.append(f"  <i>{_esc(when_str)}</i>")
    return "\n".join(lines)


def fmt_queue(items: list[dict]) -> str:
    if not items:
        return (
            "<b>UzAssets · Очередь модерации</b>\n"
            "\n"
            "Запросов на модерацию нет."
        )
    lines = [
        "<b>UzAssets · Очередь модерации</b>",
        f"Ожидают рассмотрения: <b>{len(items)}</b>",
        "",
    ]
    for it in items[:10]:
        module = it.get("module", "?")
        submitter = it.get("submitter_email") or "?"
        when = it.get("created_at")
        when_str = when.strftime("%d.%m %H:%M") if hasattr(when, "strftime") else str(when)
        lines.append(f"· <b>{_esc(str(module))}</b> от <code>{_esc(str(submitter))}</code>")
        lines.append(f"  <i>{_esc(when_str)}</i>")
    lines.append("")
    lines.append(
        f"<a href=\"{_esc(config.PLATFORM_URL)}/admin/moderation\">Открыть очередь →</a>"
    )
    return "\n".join(lines)


def fmt_sessions(sessions: list[dict]) -> str:
    if not sessions:
        return "<b>UzAssets · Сессии</b>\n\nАктивных сессий нет."
    lines = ["<b>UzAssets · Активные сессии</b>", f"Всего: <b>{len(sessions)}</b>", ""]
    for s in sessions:
        last = s.get("last_seen_at") or s.get("created_at")
        last_str = last.strftime("%d.%m %H:%M") if hasattr(last, "strftime") else str(last)
        ip = s.get("ip_address") or "—"
        ua = (s.get("user_agent") or "")[:50]
        lines.append(f"· <b>{_esc(last_str)}</b> · <code>{_esc(str(ip))}</code>")
        if ua:
            lines.append(f"  <i>{_esc(ua)}</i>")
    return "\n".join(lines)


def fmt_unlinked() -> str:
    return (
        "<b>UzAssets · Отвязка завершена</b>\n"
        "\n"
        "Telegram отвязан. Уведомления и 2FA-коды через этот чат "
        "<b>больше приходить не будут</b>.\n"
        "\n"
        f"Привязать снова: <a href=\"{_esc(config.PLATFORM_URL)}/settings/security\">"
        f"{_esc(config.PLATFORM_URL)}/settings/security</a>"
    )


def fmt_not_linked() -> str:
    return (
        "<b>UzAssets · Аккаунт не привязан</b>\n"
        "\n"
        "Этот чат не связан с аккаунтом UzAssets. Откройте платформу и привяжите Telegram:\n"
        f"<a href=\"{_esc(config.PLATFORM_URL)}/settings/security\">"
        f"{_esc(config.PLATFORM_URL)}/settings/security</a>"
    )


def fmt_link_token_invalid() -> str:
    return (
        "<b>UzAssets · Ошибка</b>\n"
        "\n"
        "Токен привязки <b>недействителен или истёк</b> (срок — 5 минут).\n"
        "\n"
        f"Откройте <a href=\"{_esc(config.PLATFORM_URL)}/settings/security\">"
        f"{_esc(config.PLATFORM_URL)}/settings/security</a> и нажмите «Связать Telegram» ещё раз."
    )


# ── Inline-keyboard builders ─────────────────────────────────────────────

def build_buttons_for_mfa(mfa_token: Optional[str] = None) -> list:
    """Inline buttons for MFA messages. mfa_token is the short-lived ID we use
    to identify the attempt for «Это не я» reporting."""
    suffix = (mfa_token or "")[:64]
    return [
        [
            {"text": "Это не я ⚠", "callback_data": f"mfa_not_me:{suffix}"},
        ],
    ]


def build_buttons_for_kpi_review(submission_id: str, deep_link: Optional[str] = None) -> list:
    rows = [
        [
            {"text": "✓ Утвердить",    "callback_data": f"kpi_approve:{submission_id}"},
            {"text": "✗ На доработку", "callback_data": f"kpi_reject:{submission_id}"},
        ],
    ]
    if deep_link:
        rows.append([{"text": "Открыть в платформе →", "url": deep_link}])
    return rows


def build_buttons_for_procurement_review(submission_id: str, deep_link: Optional[str] = None) -> list:
    rows = [
        [
            {"text": "✓ Одобрить",  "callback_data": f"procurement_approve:{submission_id}"},
            {"text": "✗ Отклонить", "callback_data": f"procurement_reject:{submission_id}"},
        ],
    ]
    if deep_link:
        rows.append([{"text": "Открыть в платформе →", "url": deep_link}])
    return rows
