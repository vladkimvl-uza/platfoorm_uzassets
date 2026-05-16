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
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import config
import db
import encryption
import formatter as fmt

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
    reply_markup = _build_markup(item.get("inline_buttons"))

    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
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
