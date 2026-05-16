"""Telegram inline-button callback handlers (Pack 13.2).

Handles `mod:approve:<uuid>` and `mod:reject:<uuid>` callbacks fired when the
user taps the inline-keyboard buttons under a moderation notification.

Flow:
  1. User taps "Принять" / "Отклонить" in Telegram.
  2. aiogram delivers a CallbackQuery → on_moderation_callback().
  3. We POST to the backend (HMAC-signed) → backend resolves chat_id → User,
     then calls moderation_service.approve / reject as that user.
  4. Backend returns ok=True + new_status.
  5. We edit the Telegram message — replace inline kbd with a status line.
"""
import hashlib
import hmac
import json
import logging
from typing import Optional

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

import config

log = logging.getLogger("uza-bot.callbacks")

router = Router()

_PLATFORM_API_URL = (
    getattr(config, "PLATFORM_API_URL", None)
    or getattr(config, "PLATFORM_URL", "https://localhost").rstrip("/") + "/api"
)
_BOT_CALLBACK_SECRET = getattr(config, "BOT_CALLBACK_SECRET", "") or ""


async def _signed_post(path: str, body: dict) -> tuple[int, dict]:
    """POST to backend with HMAC-SHA256 signature header. Returns (status, json)."""
    if not _BOT_CALLBACK_SECRET:
        return 500, {"detail": "BOT_CALLBACK_SECRET not configured"}

    url = f"{_PLATFORM_API_URL.rstrip('/')}{path}"
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sig = hmac.new(_BOT_CALLBACK_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Bot-Signature": sig,
    }

    try:
        # Self-signed dev certs are common — disable verify in dev. In prod set
        # PLATFORM_API_URL to the public hostname with a valid cert.
        verify = not _PLATFORM_API_URL.startswith("https://localhost")
        async with httpx.AsyncClient(timeout=15.0, verify=verify) as client:
            r = await client.post(url, content=raw, headers=headers)
            try:
                data = r.json()
            except Exception:
                data = {"detail": r.text[:300] if r.text else "no body"}
            return r.status_code, data
    except Exception as e:
        log.warning("Backend call failed: %s", e)
        return 599, {"detail": f"connection error: {e}"}


async def _strip_kbd_and_append(cq: CallbackQuery, status_line: str) -> None:
    """Edit the original message: clear inline keyboard, append a status footer."""
    msg = cq.message
    if msg is None:
        return
    original_text = msg.text or msg.caption or ""
    new_text = original_text + "\n\n" + status_line
    try:
        await msg.edit_text(new_text, reply_markup=None)
    except TelegramBadRequest as e:
        # Sometimes message has no text (only buttons). Fallback to caption / answer.
        log.info("edit_text failed: %s. Falling back to answer.", e)
        try:
            await cq.answer(status_line, show_alert=True)
        except Exception:
            pass


# ─── mod:approve:<id> ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mod:approve:"))
async def on_moderation_approve(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    sub_id = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not sub_id:
        await cq.answer("Некорректный ID.", show_alert=True)
        return

    await cq.answer("Принимаем…")  # acknowledge immediately

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/moderation/approve",
        {"chat_id": chat_id, "submission_id": sub_id},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(cq, "[ПРИНЯТО]\nПодтверждено через Telegram.")
    elif code == 404:
        await cq.answer("Telegram аккаунт не привязан или вы не имеете прав.", show_alert=True)
    elif code == 401:
        await cq.answer("Доступ запрещён. Проверьте настройки бота.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось принять: {detail}", show_alert=True)


# ─── mod:reject:<id> ─────────────────────────────────────────────────

# ─── tglink:confirm:<token> ──────────────────────────────────────────
# Pack 13.3: user tapped "Это я" on the link-confirmation card.

@router.callback_query(F.data.startswith("tglink:confirm:"))
async def on_tglink_confirm(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    token = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not token:
        await cq.answer("Некорректный токен.", show_alert=True)
        return

    await cq.answer("Привязываем…")

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/tg-link/confirm",
        {
            "chat_id": chat_id,
            "token": token,
            "username": cq.from_user.username or "",
        },
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(
            cq,
            "[✓ ПРИВЯЗАНО]
"
            f"Telegram привязан к аккаунту {data.get('email', '')}.
"
            "Можно вернуться в браузер."
        )
    elif code == 410:
        await cq.answer("Токен истёк. Откройте окно настройки заново.", show_alert=True)
    elif code == 404:
        await cq.answer("Токен не найден. Возможно, он уже использован.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось привязать: {detail}", show_alert=True)


# ─── tglink:deny:<token> ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("tglink:deny:"))
async def on_tglink_deny(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    token = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not token:
        await cq.answer()
        return

    await cq.answer("Отменяем…")

    chat_id = cq.from_user.id
    await _signed_post(
        "/bot/tg-link/deny",
        {"chat_id": chat_id, "token": token},
    )

    await _strip_kbd_and_append(
        cq,
        "[ОТМЕНЕНО]
"
        "Привязка отменена. Если это были не вы — сообщите администратору, "
        "что кто-то получил доступ к ссылке привязки."
    )


@router.callback_query(F.data.startswith("mod:reject:"))
async def on_moderation_reject(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    sub_id = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not sub_id:
        await cq.answer("Некорректный ID.", show_alert=True)
        return

    await cq.answer("Отклоняем…")

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/moderation/reject",
        {"chat_id": chat_id, "submission_id": sub_id},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(cq, "[ОТКЛОНЕНО]\nОтклонено через Telegram.")
    elif code == 404:
        await cq.answer("Telegram аккаунт не привязан или вы не имеете прав.", show_alert=True)
    elif code == 401:
        await cq.answer("Доступ запрещён. Проверьте настройки бота.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось отклонить: {detail}", show_alert=True)
