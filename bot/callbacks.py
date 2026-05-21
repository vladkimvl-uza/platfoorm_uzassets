"""Telegram inline-button callback handlers.

Phase A (premium upgrade) — HTML-formatted edits, module-specific actions.

Endpoints contract (HMAC-signed POST → backend):
  /bot/moderation/approve            generic moderation accept
  /bot/moderation/reject             generic moderation reject
  /bot/tg-link/confirm               two-step Telegram link confirm
  /bot/tg-link/deny                  two-step Telegram link deny
  /bot/tg-callbacks/mfa-report       "Это не я" on MFA prompt
  /bot/tg-callbacks/kpi/{id}/decision        approve | reject
  /bot/tg-callbacks/procurement/{id}/decision approve | reject
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


# =====================================================================
# Signed POST helper
# =====================================================================

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
    """Edit the original message: clear inline keyboard, append HTML status footer.

    `status_line` is treated as HTML (Phase A — all messages use parse_mode=HTML)."""
    msg = cq.message
    if msg is None:
        return
    original_html = msg.html_text if getattr(msg, "html_text", None) else (msg.text or msg.caption or "")
    new_text = original_html + "\n\n" + status_line
    try:
        await msg.edit_text(new_text, reply_markup=None, disable_web_page_preview=True)
    except TelegramBadRequest as e:
        log.info("edit_text failed: %s. Falling back to answer.", e)
        try:
            await cq.answer(status_line, show_alert=True)
        except Exception:
            pass


# =====================================================================
# Generic moderation (Pack 13.2)
# =====================================================================

@router.callback_query(F.data.startswith("mod:approve:"))
async def on_moderation_approve(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    sub_id = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not sub_id:
        await cq.answer("Некорректный ID.", show_alert=True)
        return

    await cq.answer("Принимаем…")
    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/moderation/approve",
        {"chat_id": chat_id, "submission_id": sub_id},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(cq, "<b>✓ ПРИНЯТО</b>\n<i>Подтверждено через Telegram.</i>")
    elif code == 404:
        await cq.answer("Telegram аккаунт не привязан или вы не имеете прав.", show_alert=True)
    elif code == 401:
        await cq.answer("Доступ запрещён. Проверьте настройки бота.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось принять: {detail}", show_alert=True)


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
        await _strip_kbd_and_append(cq, "<b>✗ ОТКЛОНЕНО</b>\n<i>Отклонено через Telegram.</i>")
    elif code == 404:
        await cq.answer("Telegram аккаунт не привязан или вы не имеете прав.", show_alert=True)
    elif code == 401:
        await cq.answer("Доступ запрещён. Проверьте настройки бота.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось отклонить: {detail}", show_alert=True)


# =====================================================================
# Telegram link two-step (Pack 13.3)
# =====================================================================

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
        email = data.get("email", "")
        await _strip_kbd_and_append(
            cq,
            "<b>✓ ПРИВЯЗАНО</b>\n"
            f"Telegram привязан к аккаунту <code>{email}</code>.\n"
            "<i>Можно вернуться в браузер.</i>",
        )
    elif code == 410:
        await cq.answer("Токен истёк. Откройте окно настройки заново.", show_alert=True)
    elif code == 404:
        await cq.answer("Токен не найден. Возможно, он уже использован.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось привязать: {detail}", show_alert=True)


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
        "<b>⊘ ОТМЕНЕНО</b>\n"
        "<i>Привязка отменена. Если это были не вы — сообщите администратору, "
        "что кто-то получил доступ к ссылке привязки.</i>",
    )


# =====================================================================
# Phase A — module-specific quick actions
# =====================================================================

# ─── mfa_not_me:<token> ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("mfa_not_me:"))
async def on_mfa_not_me(cq: CallbackQuery) -> None:
    """User reported a suspicious MFA prompt. Backend logs as security_flag
    and invalidates the in-flight code."""
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    mfa_token = cq.data.split(":", 1)[1] if ":" in cq.data else ""
    await cq.answer("Сообщаем…")

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/tg-callbacks/mfa-report",
        {"chat_id": chat_id, "mfa_token": mfa_token},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(
            cq,
            "<b>⚠ Сообщение отправлено</b>\n"
            "<i>Безопасность уведомлена. Рекомендуем сменить пароль.</i>",
        )
    elif code == 404:
        await cq.answer("Telegram аккаунт не привязан.", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось сообщить: {detail}", show_alert=True)


# ─── kpi_approve / kpi_reject :<submission_id> ───────────────────────

@router.callback_query(F.data.startswith("kpi_approve:"))
async def on_kpi_approve(cq: CallbackQuery) -> None:
    await _module_decision(cq, module="kpi", decision="approve")


@router.callback_query(F.data.startswith("kpi_reject:"))
async def on_kpi_reject(cq: CallbackQuery) -> None:
    await _module_decision(cq, module="kpi", decision="reject")


# ─── procurement_approve / procurement_reject :<submission_id> ───────

@router.callback_query(F.data.startswith("procurement_approve:"))
async def on_procurement_approve(cq: CallbackQuery) -> None:
    await _module_decision(cq, module="procurement", decision="approve")


@router.callback_query(F.data.startswith("procurement_reject:"))
async def on_procurement_reject(cq: CallbackQuery) -> None:
    await _module_decision(cq, module="procurement", decision="reject")


async def _module_decision(cq: CallbackQuery, *, module: str, decision: str) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    sub_id = cq.data.split(":", 1)[1] if ":" in cq.data else ""
    if not sub_id:
        await cq.answer("Некорректный ID.", show_alert=True)
        return

    await cq.answer("Отправляем решение…")

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        f"/bot/tg-callbacks/{module}/{sub_id}/decision",
        {"chat_id": chat_id, "decision": decision},
    )

    label_ok = "<b>✓ УТВЕРЖДЕНО</b>" if decision == "approve" else "<b>✗ НА ДОРАБОТКУ</b>"
    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(
            cq, f"{label_ok}\n<i>Действие выполнено через Telegram.</i>"
        )
    elif code == 404:
        await cq.answer("Telegram аккаунт не привязан или объект не найден.", show_alert=True)
    elif code == 403:
        await cq.answer("Нет прав на это действие.", show_alert=True)
    elif code == 409:
        detail = data.get("detail", "уже обработано")
        await cq.answer(f"Конфликт: {detail}", show_alert=True)
    else:
        detail = data.get("detail", "ошибка")
        await cq.answer(f"Не удалось: {detail}", show_alert=True)


# =====================================================================
# Mention reply — inline reply via chat (simple "expect-next-message" state)
# =====================================================================

import time as _time
_PENDING_REPLIES: dict[int, dict] = {}


@router.callback_query(F.data.startswith("mention_reply:"))
async def on_mention_reply(cq: CallbackQuery) -> None:
    """User clicked «Ответить в чате» — set pending-reply state, ask for next msg."""
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer(); return
    parts = cq.data.split(":", 2)
    if len(parts) != 3:
        await cq.answer("Некорректный callback", show_alert=True); return
    _, ent_type, ent_id = parts

    _PENDING_REPLIES[cq.from_user.id] = {
        "entity_type": ent_type,
        "entity_id": ent_id,
        "expires_at": _time.time() + 600,
    }
    await cq.answer("Жду ваш ответ — следующее сообщение станет комментарием")
    try:
        await cq.message.reply(
            "<b>💬 Напишите ответ</b>\n\n"
            "Следующее ваше сообщение в этом чате будет добавлено как комментарий "
            "к задаче/проекту на платформе. Можете использовать @-упоминания. "
            "Чтобы отменить — отправьте /cancel"
        )
    except Exception as e:
        log.warning("mention_reply: reply failed: %s", e)


def get_pending_reply(chat_id: int) -> Optional[dict]:
    """Helper for handlers.py: get + auto-expire pending reply state."""
    state = _PENDING_REPLIES.get(chat_id)
    if not state:
        return None
    if _time.time() > state.get("expires_at", 0):
        _PENDING_REPLIES.pop(chat_id, None)
        return None
    return state


def clear_pending_reply(chat_id: int) -> None:
    _PENDING_REPLIES.pop(chat_id, None)
