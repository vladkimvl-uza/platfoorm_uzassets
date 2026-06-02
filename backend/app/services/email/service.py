"""Отправка e-mail (SMTP).

Использует стандартный smtplib в thread-executor (без доп. зависимостей).
Если SMTP не сконфигурирован (SMTP_ENABLED=false или пустой SMTP_HOST) —
graceful no-op + лог: остальной код вызывает send_* безопасно и не падает.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.config import settings
from app.services.email import templates
from app.services.email.runtime_config import effective

log = logging.getLogger(__name__)


def email_configured() -> bool:
    cfg = effective()
    return bool(cfg.get("SMTP_ENABLED") and cfg.get("SMTP_HOST"))


def _send_sync(to: str, subject: str, html: str) -> None:
    cfg = effective()
    msg = EmailMessage()
    msg["From"] = cfg.get("SMTP_FROM") or settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(
        "Это письмо в формате HTML. Откройте его в почтовом клиенте с поддержкой HTML."
    )
    msg.add_alternative(html, subtype="html")

    host = cfg.get("SMTP_HOST"); port = int(cfg.get("SMTP_PORT") or 587)
    user = cfg.get("SMTP_USER"); pwd = cfg.get("SMTP_PASSWORD")
    timeout = settings.SMTP_TIMEOUT
    ctx = ssl.create_default_context()
    if cfg.get("SMTP_USE_SSL"):
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ctx) as s:
            if user:
                s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=timeout) as s:
            if cfg.get("SMTP_USE_TLS"):
                s.starttls(context=ctx)
            if user:
                s.login(user, pwd)
            s.send_message(msg)


async def send_email(to: str, subject: str, html: str) -> bool:
    """Отправить письмо. Возвращает True при успехе, False если пропущено/ошибка.
    Никогда не бросает исключение наружу (best-effort)."""
    if not email_configured():
        log.info("email skipped (SMTP disabled): to=%s subject=%r", to, subject)
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, html)
        log.info("email sent: to=%s subject=%r", to, subject)
        return True
    except Exception:  # noqa: BLE001 — best-effort, не валим вызывающий код
        log.warning("email send failed: to=%s subject=%r", to, subject, exc_info=True)
        return False


# ── Convenience-сендеры (используют брендовые шаблоны) ───────────────

async def send_mfa_code_email(*, to: str, code: str, ip: str | None = None,
                              when: str | None = None) -> bool:
    subject, html = templates.mfa_code_email(code=code, email=to, ip=ip, when=when)
    return await send_email(to, subject, html)


async def send_invite_email(*, to: str, full_name: str, temp_password: str,
                            must_change: bool = True) -> bool:
    login_url = str(effective().get("PUBLIC_URL") or settings.PUBLIC_URL).rstrip("/") + "/login"
    subject, html = templates.invite_email(
        full_name=full_name, email=to, temp_password=temp_password,
        login_url=login_url, must_change=must_change,
    )
    return await send_email(to, subject, html)


async def send_generic_email(*, to: str, eyebrow: str, title: str,
                             body_lines: list[str], button_label: str | None = None,
                             button_url: str | None = None, accent: str | None = None) -> bool:
    subject, html = templates.generic_email(
        eyebrow=eyebrow, title=title, body_lines=body_lines,
        button_label=button_label, button_url=button_url,
        accent=accent or templates._PURPLE,
    )
    return await send_email(to, subject, html)


__all__ = [
    "email_configured", "send_email", "send_mfa_code_email",
    "send_invite_email", "send_generic_email",
]
