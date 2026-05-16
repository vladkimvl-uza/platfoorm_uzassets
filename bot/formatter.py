"""Format outbox payloads into Telegram message text.

Style: no emoji, text markers in brackets ([CODE], [DEADLINE], [MOD], [OK], etc).
"""
from typing import Optional

import config


def format_outbox(msg_type: str, payload: dict, email: str) -> str:
    """Dispatch on message type → render text body."""
    handlers = {
        "mfa_code":          _fmt_mfa_code,
        "link_confirmation": _fmt_link_confirmation,
        "notification":      _fmt_notification,
        "test":              _fmt_test,
    }
    h = handlers.get(msg_type, _fmt_unknown)
    return h(payload, email)


# ── Specific renderers ────────────────────────────────────────────────────

def _fmt_mfa_code(p: dict, email: str) -> str:
    code = str(p.get("code", "?"))
    # Format as "384 721" for readability
    pretty = code[:3] + " " + code[3:] if len(code) == 6 else code
    ttl = p.get("ttl_minutes", 5)
    ip = p.get("ip") or "—"
    lines = [
        "[UzAssets · код доступа]",
        "",
        f"Код:   {pretty}",
        f"Срок:  {ttl} минут",
        "",
        f"Аккаунт: {email}",
        f"IP:      {ip}",
        "",
        "Если это были не вы — проигнорируйте сообщение и проверьте безопасность аккаунта.",
    ]
    return "\n".join(lines)


def _fmt_link_confirmation(p: dict, email: str) -> str:
    return (
        "[UzAssets · привязка успешна]\n"
        "\n"
        f"Аккаунт: {email}\n"
        "\n"
        "Теперь при входе вам будет приходить код доступа в этом чате. "
        "Также вы можете включить дублирование уведомлений из платформы "
        "(назначения, дедлайны, модерация) в настройках:\n"
        f"{config.PLATFORM_URL}/settings/security"
    )


def _fmt_notification(p: dict, email: str) -> str:
    """Generic notification — backend sets title/body/deep_link/marker."""
    marker = p.get("marker") or "[Уведомление]"
    title  = p.get("title", "Уведомление")
    body   = p.get("body", "")
    deep_link = p.get("deep_link")
    actor  = p.get("actor")
    when   = p.get("when")  # ISO timestamp or human-readable

    parts = [marker, "", title]
    if body:
        parts.extend(["", body])
    if actor or when:
        parts.append("")
        if actor: parts.append(f"От:    {actor}")
        if when:  parts.append(f"Когда: {when}")
    if deep_link:
        parts.extend(["", f"Открыть → {deep_link}"])
    return "\n".join(parts)


def _fmt_test(p: dict, email: str) -> str:
    title = p.get("title", "Тестовое уведомление UzAssets")
    body  = p.get("body", "Доставка через Telegram работает корректно.")
    return (
        "[UzAssets · тест]\n"
        "\n"
        f"{title}\n"
        "\n"
        f"{body}\n"
        "\n"
        f"Аккаунт: {email}"
    )


def _fmt_unknown(p: dict, email: str) -> str:
    return f"[UzAssets]\n\n{p}\n\nАккаунт: {email}"


# ── Command response helpers ──────────────────────────────────────────────

def fmt_help() -> str:
    return (
        "[UzAssets bot · справка]\n"
        "\n"
        "Команды:\n"
        "/start <токен>  — привязать аккаунт\n"
        "/status         — мои последние уведомления\n"
        "/queue          — модерация (для модераторов)\n"
        "/sessions       — мои активные сессии\n"
        "/unlink         — отвязать Telegram\n"
        "/help           — эта справка\n"
        "\n"
        f"Платформа: {config.PLATFORM_URL}\n"
        f"Поддержка: v.kim@uz-assets.uz"
    )


def fmt_welcome_no_token() -> str:
    return (
        "[UzAssets bot]\n"
        "\n"
        "Здравствуйте. Чтобы связать аккаунт с этим чатом:\n"
        "1. Откройте платформу UzAssets\n"
        "2. Настройки → Безопасность → Связать Telegram\n"
        "3. Нажмите большую синюю кнопку с QR-кодом (или скопируйте ссылку)\n"
        "\n"
        "Затем эта кнопка приведёт вас обратно сюда с токеном привязки.\n"
        "\n"
        f"Платформа: {config.PLATFORM_URL}/settings/security\n"
        "\n"
        "Полный список команд: /help"
    )


def fmt_status(user_email: str, notifications: list[dict]) -> str:
    if not notifications:
        return (
            f"[UzAssets · {user_email}]\n"
            "\n"
            "Непрочитанных уведомлений нет."
        )
    lines = [f"[UzAssets · {user_email}]", f"Непрочитанных: {len(notifications)}", ""]
    for n in notifications[:5]:
        title = n.get("title") or n.get("type") or "(без заголовка)"
        when = n.get("created_at")
        when_str = when.strftime("%d.%m %H:%M") if hasattr(when, "strftime") else str(when)
        lines.append(f"· {title}")
        lines.append(f"  {when_str}")
    return "\n".join(lines)


def fmt_queue(items: list[dict]) -> str:
    if not items:
        return "[UzAssets · очередь модерации]\n\nЗапросов на модерацию нет."
    lines = ["[UzAssets · очередь модерации]", f"Ожидают рассмотрения: {len(items)}", ""]
    for it in items[:10]:
        module = it.get("module", "?")
        submitter = it.get("submitter_email") or "?"
        when = it.get("created_at")
        when_str = when.strftime("%d.%m %H:%M") if hasattr(when, "strftime") else str(when)
        lines.append(f"· {module} от {submitter}")
        lines.append(f"  {when_str}")
    lines.append("")
    lines.append(f"Открыть очередь: {config.PLATFORM_URL}/admin/moderation")
    return "\n".join(lines)


def fmt_sessions(sessions: list[dict]) -> str:
    if not sessions:
        return "[UzAssets · сессии]\n\nАктивных сессий нет."
    lines = ["[UzAssets · активные сессии]", f"Всего: {len(sessions)}", ""]
    for s in sessions:
        last = s.get("last_seen_at") or s.get("created_at")
        last_str = last.strftime("%d.%m %H:%M") if hasattr(last, "strftime") else str(last)
        ip = s.get("ip_address") or "—"
        ua = (s.get("user_agent") or "")[:50]
        lines.append(f"· {last_str} от {ip}")
        if ua: lines.append(f"  {ua}")
    return "\n".join(lines)


def fmt_unlinked() -> str:
    return (
        "[UzAssets · отвязка завершена]\n"
        "\n"
        "Telegram отвязан. Уведомления и 2FA-коды через этот чат больше приходить не будут.\n"
        "\n"
        f"Привязать снова: {config.PLATFORM_URL}/settings/security"
    )


def fmt_not_linked() -> str:
    return (
        "[UzAssets · аккаунт не привязан]\n"
        "\n"
        "Этот чат не связан с аккаунтом UzAssets. Откройте платформу и привяжите Telegram:\n"
        f"{config.PLATFORM_URL}/settings/security"
    )


def fmt_link_token_invalid() -> str:
    return (
        "[UzAssets · ошибка]\n"
        "\n"
        "Токен привязки недействителен или истёк (срок действия — 5 минут).\n"
        "\n"
        f"Откройте {config.PLATFORM_URL}/settings/security и нажмите «Связать Telegram» ещё раз."
    )


def fmt_link_success(email: str) -> str:
    return (
        "[UzAssets · привязка успешна]\n"
        "\n"
        f"Аккаунт {email} связан с этим чатом.\n"
        "\n"
        "Теперь при входе в платформу вы будете получать сюда код доступа. "
        "Также можете включить уведомления о задачах, дедлайнах и модерации:\n"
        f"{config.PLATFORM_URL}/settings/security\n"
        "\n"
        "Команды: /help"
    )
