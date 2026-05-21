"""Outbox worker — polls telegram_outbox table every N seconds, delivers messages.

Runs concurrently with aiogram polling in the same asyncio event loop.
"""
import asyncio
import json
import logging
import time
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError,
    TelegramRetryAfter, TelegramAPIError,
)
from aiogram.types import (
    BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, URLInputFile,
)
import httpx

import config
import db
import encryption
import formatter as fmt

# Telegram caption hard limit (photo + caption combined message)
_TELEGRAM_CAPTION_LIMIT = 1024

log = logging.getLogger("uza-bot.outbox")

HEARTBEAT_FILE = "/tmp/uza-tg-bot-heartbeat"


async def loop(bot: Bot) -> None:
    """Main worker loop. Run as a task alongside dp.start_polling()."""
    log.info("Outbox worker started (poll interval %.1fs)", config.OUTBOX_POLL_SEC)
    while True:
        try:
            # Heartbeat for docker healthcheck
            try:
                with open(HEARTBEAT_FILE, "w") as f:
                    f.write(str(int(time.time())))
            except Exception:
                pass

            count = await _process_batch(bot)
            if count == 0:
                await asyncio.sleep(config.OUTBOX_POLL_SEC)
            else:
                # Found work — poll again immediately for the next batch
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            log.info("Outbox worker cancelled; exiting")
            raise
        except Exception:
            log.exception("Outbox loop error; sleeping and retrying")
            await asyncio.sleep(config.OUTBOX_POLL_SEC * 2)


async def _process_batch(bot: Bot) -> int:
    items = await db.fetch_pending_outbox(limit=config.OUTBOX_BATCH_SIZE)
    if not items:
        return 0
    for item in items:
        await _deliver_one(bot, item)
    return len(items)


async def _deliver_one(bot: Bot, item: dict) -> None:
    outbox_id = item["id"]
    msg_type = item["type"]
    user_email = item.get("email") or "unknown"

    # Need chat_id (decrypted)
    chat_enc = item.get("telegram_chat_id_encrypted")
    if not chat_enc:
        log.warning("outbox %s: user has no telegram_chat_id, discarding", outbox_id)
        await db.mark_outbox_discarded(outbox_id, "user has no telegram_chat_id")
        return

    try:
        chat_id = encryption.decrypt_int(chat_enc)
    except Exception as e:
        log.warning("outbox %s: failed to decrypt chat_id: %s", outbox_id, e)
        await db.mark_outbox_discarded(outbox_id, f"decrypt failed: {e}")
        return

    payload = item.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {"raw": payload}

    text = fmt.format_outbox(msg_type, payload, user_email)
    # inline_buttons may live on the outbox row OR inside the payload (Phase A)
    inline_buttons = item.get("inline_buttons") or payload.get("inline_buttons")
    reply_markup = _build_markup(inline_buttons)

    # parse_mode override per item — formatter now returns HTML by default,
    # so we let the bot's default (HTML) apply unless explicitly set otherwise.
    parse_mode_override = payload.get("parse_mode")

    # Phase B: photo banner — send_photo(caption=...) when payload requests it
    # AND the caption fits Telegram's 1024-char limit. Otherwise fall back to
    # send_message (the 4096-char text body).
    want_banner = bool(payload.get("banner")) and bool(payload.get("banner_url"))
    use_photo = want_banner and len(text) <= _TELEGRAM_CAPTION_LIMIT

    try:
        if use_photo:
            # Fetch banner bytes via internal network and send as multipart
            # upload — Telegram cannot reach private hostnames (uz-assets040,
            # platform internal). Bot is in the same Docker network as the
            # backend so internal URL works.
            photo_input = await _fetch_banner_as_bytes(payload["banner_url"])
            if photo_input is None:
                # Fallback: text-only message if banner fetch failed
                log.warning("outbox %s: banner fetch failed, falling back to text", outbox_id)
                msg = await bot.send_message(
                    chat_id=chat_id, text=text,
                    reply_markup=reply_markup, disable_web_page_preview=True,
                    parse_mode=parse_mode_override,
                )
            else:
                send_kwargs = dict(
                    chat_id=chat_id,
                    photo=photo_input,
                    caption=text,
                    reply_markup=reply_markup,
                )
                if parse_mode_override is not None:
                    send_kwargs["parse_mode"] = parse_mode_override
                msg = await bot.send_photo(**send_kwargs)
        else:
            send_kwargs = dict(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
            if parse_mode_override is not None:
                send_kwargs["parse_mode"] = parse_mode_override
            msg = await bot.send_message(**send_kwargs)
        await db.mark_outbox_sent(outbox_id, msg.message_id)
        log.info("outbox %s delivered to %s (msg_id=%s)", outbox_id, user_email, msg.message_id)
    except TelegramForbiddenError as e:
        # User blocked the bot — discard, no retry
        log.warning("outbox %s: user blocked bot (%s)", outbox_id, e)
        await db.mark_outbox_discarded(outbox_id, f"forbidden: {e}")
    except TelegramRetryAfter as e:
        log.warning("outbox %s: flood limit, retry after %ss", outbox_id, e.retry_after)
        await db.mark_outbox_failed(outbox_id, f"flood: retry after {e.retry_after}s")
        # Sleep to let other bots also back off — coarse but effective
        await asyncio.sleep(min(e.retry_after, 30))
    except TelegramBadRequest as e:
        log.warning("outbox %s: bad request (%s)", outbox_id, e)
        await db.mark_outbox_discarded(outbox_id, f"bad request: {e}")
    except TelegramAPIError as e:
        log.warning("outbox %s: api error (%s)", outbox_id, e)
        await db.mark_outbox_failed(outbox_id, str(e))
    except Exception as e:
        log.exception("outbox %s: unexpected error", outbox_id)
        await db.mark_outbox_failed(outbox_id, str(e))


async def _fetch_banner_as_bytes(url: str) -> Optional[BufferedInputFile]:
    """Fetch banner from URL (internal network) and wrap as BufferedInputFile.
    Returns None on any failure — caller falls back to text-only message.

    URL rewriting: if the URL points at platform.uz-assets.uz / uz-assets040
    (public hostnames Telegram can't reach), swap to internal Docker
    hostname `backend:8000` for the actual HTTP request.
    """
    internal_url = url
    for public_host in ("https://platform.uz-assets.uz", "https://uz-assets040",
                        "https://uzassets006", "http://platform.uz-assets.uz"):
        if internal_url.startswith(public_host):
            # Map public → internal Docker DNS name
            internal_url = internal_url.replace(public_host, "http://backend:8000", 1)
            # Drop "/api" since the backend itself is mounted at /
            internal_url = internal_url.replace("http://backend:8000/api/", "http://backend:8000/", 1)
            break

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(internal_url)
            r.raise_for_status()
            return BufferedInputFile(r.content, filename="uza-banner.png")
    except Exception as e:
        log.warning("banner fetch failed: %s url=%s", e, internal_url)
        return None


def _build_markup(inline_buttons) -> Optional[InlineKeyboardMarkup]:
    """inline_buttons: list of {text, callback_data} OR list of lists for rows."""
    if not inline_buttons:
        return None
    if isinstance(inline_buttons, str):
        try:
            inline_buttons = json.loads(inline_buttons)
        except Exception:
            return None
    if not isinstance(inline_buttons, list):
        return None

    # Normalize to list-of-rows
    if inline_buttons and isinstance(inline_buttons[0], dict):
        inline_buttons = [inline_buttons]  # single row

    rows = []
    for row in inline_buttons:
        btns = []
        for b in row:
            if not isinstance(b, dict): continue
            text = b.get("text", "?")
            cb = b.get("callback_data")
            url = b.get("url")
            if cb:
                btns.append(InlineKeyboardButton(text=text, callback_data=cb))
            elif url:
                btns.append(InlineKeyboardButton(text=text, url=url))
        if btns:
            rows.append(btns)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
