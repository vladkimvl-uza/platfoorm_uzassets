"""Production 5xx Telegram alerter.

Posts an alert to admin chat(s) when an unhandled exception escapes a
request handler. Triggered from `app.core.error_handlers.unhandled_handler`.

Design choices:
  - Direct HTTP to api.telegram.org (no DB at exception time — the DB
    might be the very thing that broke).
  - In-memory throttle keyed by (endpoint, exc_type) — 5 min cooldown
    prevents storms when one bad route fires repeatedly.
  - No-op if ADMIN_ALERT_CHAT_IDS or TELEGRAM_BOT_TOKEN unset (dev /
    misconfigured prod). Logs a warning and returns.
  - Best-effort: any failure in the alerter itself is swallowed and logged.
    The user's 500 response is never delayed because of TG.

Env:
  TELEGRAM_BOT_TOKEN       — bot token (same as outbox worker uses)
  ADMIN_ALERT_CHAT_IDS     — comma-separated chat IDs (e.g. "123,456")
  ALERT_THROTTLE_SECONDS   — cooldown per (endpoint, exc_type), default 300
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
from html import escape as _esc

import httpx

logger = logging.getLogger(__name__)

_last_sent: dict[tuple[str, str], float] = {}


def _admin_chat_ids() -> list[str]:
    raw = (os.getenv("ADMIN_ALERT_CHAT_IDS") or "").strip()
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


def _throttle_seconds() -> int:
    try:
        return int(os.getenv("ALERT_THROTTLE_SECONDS", "300"))
    except ValueError:
        return 300


def _should_send(key: tuple[str, str]) -> bool:
    now = time.monotonic()
    last = _last_sent.get(key, 0.0)
    if now - last < _throttle_seconds():
        return False
    _last_sent[key] = now
    return True


async def _post(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
        )
        if r.status_code >= 400:
            logger.warning("TG alert send failed: %s %s", r.status_code, r.text[:200])


def _format_alert(method: str, path: str, exc: BaseException,
                  request_id: str | None, user_id: str | None) -> str:
    exc_type = type(exc).__name__
    msg = str(exc)[:600]
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # Keep total under ~3500 chars (Telegram limit 4096).
    tb_short = tb[-2400:] if len(tb) > 2400 else tb

    lines = [
        "<b>UzAssets · 5xx ALERT</b>",
        "",
        f"<b>{_esc(exc_type)}</b>: {_esc(msg)}",
        "",
        f"<code>{_esc(method)} {_esc(path)}</code>",
    ]
    if request_id:
        lines.append(f"request_id: <code>{_esc(request_id)}</code>")
    if user_id:
        lines.append(f"user_id: <code>{_esc(user_id)}</code>")
    lines.extend(["", "<pre>" + _esc(tb_short) + "</pre>"])
    return "\n".join(lines)


async def send_5xx_alert(
    *,
    exc: BaseException,
    method: str,
    path: str,
    request_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """Fire-and-forget alert. Never raises."""
    try:
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        chats = _admin_chat_ids()
        if not token or not chats:
            return  # silently no-op in dev / misconfigured prod

        key = (path, type(exc).__name__)
        if not _should_send(key):
            return

        text = _format_alert(method, path, exc, request_id, user_id)
        # Fan-out to all admin chats concurrently.
        await asyncio.gather(
            *[_post(token, c, text) for c in chats],
            return_exceptions=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("error_alerter itself failed")
