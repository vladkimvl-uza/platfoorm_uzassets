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
import db
from i18n import locale_from_telegram, msg, normalize_locale

log = logging.getLogger("uza-bot.callbacks")

router = Router()

_PLATFORM_API_URL = (
    getattr(config, "PLATFORM_API_URL", None)
    or getattr(config, "PLATFORM_URL", "https://localhost").rstrip("/") + "/api"
)
_BOT_CALLBACK_SECRET = getattr(config, "BOT_CALLBACK_SECRET", "") or ""


async def _callback_locale(cq: CallbackQuery, link_token: str = "") -> str:
    fallback = locale_from_telegram(
        getattr(cq.from_user, "language_code", None) if cq.from_user else None
    )
    if cq.from_user is None:
        return fallback
    try:
        user = await db.find_user_by_chat_id(cq.from_user.id)
        if user is None and link_token:
            user = await db.lookup_user_by_link_token(link_token)
        if user:
            return normalize_locale(user.get("ui_locale"))
    except Exception as exc:
        log.debug("Could not resolve callback locale: %s", exc)
    return fallback


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
# Generic moderation # =====================================================================

@router.callback_query(F.data.startswith("mod:approve:"))
async def on_moderation_approve(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    locale = await _callback_locale(cq)
    sub_id = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not sub_id:
        await cq.answer(msg("invalid_id", locale), show_alert=True)
        return

    await cq.answer(msg("accepting", locale))
    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/moderation/approve",
        {"chat_id": chat_id, "submission_id": sub_id},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(cq, msg("accepted_footer", locale))
    elif code == 404:
        await cq.answer(msg("account_or_permission_missing", locale), show_alert=True)
    elif code == 401:
        await cq.answer(msg("bot_access_denied", locale), show_alert=True)
    else:
        detail = data.get("detail", str(code))
        await cq.answer(msg("accept_failed", locale, detail=detail), show_alert=True)


@router.callback_query(F.data.startswith("mod:reject:"))
async def on_moderation_reject(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    locale = await _callback_locale(cq)
    sub_id = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    if not sub_id:
        await cq.answer(msg("invalid_id", locale), show_alert=True)
        return

    await cq.answer(msg("rejecting", locale))
    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/moderation/reject",
        {"chat_id": chat_id, "submission_id": sub_id},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(cq, msg("rejected_footer", locale))
    elif code == 404:
        await cq.answer(msg("account_or_permission_missing", locale), show_alert=True)
    elif code == 401:
        await cq.answer(msg("bot_access_denied", locale), show_alert=True)
    else:
        detail = data.get("detail", str(code))
        await cq.answer(msg("reject_failed", locale, detail=detail), show_alert=True)


# =====================================================================
# Telegram link two-step # =====================================================================

@router.callback_query(F.data.startswith("tglink:confirm:"))
async def on_tglink_confirm(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    token = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    locale = await _callback_locale(cq, token)
    if not token:
        await cq.answer(msg("invalid_link_token", locale), show_alert=True)
        return

    await cq.answer(msg("linking", locale))
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
        await _strip_kbd_and_append(cq, msg("linked_footer", locale, email=email))
    elif code == 410:
        await cq.answer(msg("link_token_expired", locale), show_alert=True)
    elif code == 404:
        await cq.answer(msg("link_token_not_found", locale), show_alert=True)
    else:
        detail = data.get("detail", str(code))
        await cq.answer(msg("link_failed", locale, detail=detail), show_alert=True)


@router.callback_query(F.data.startswith("tglink:deny:"))
async def on_tglink_deny(cq: CallbackQuery) -> None:
    if cq.data is None or cq.message is None or cq.from_user is None:
        await cq.answer()
        return

    token = cq.data.split(":", 2)[2] if cq.data.count(":") >= 2 else ""
    locale = await _callback_locale(cq, token)
    if not token:
        await cq.answer()
        return

    await cq.answer(msg("cancelling", locale))
    chat_id = cq.from_user.id
    await _signed_post(
        "/bot/tg-link/deny",
        {"chat_id": chat_id, "token": token},
    )

    await _strip_kbd_and_append(cq, msg("link_cancelled_footer", locale))


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

    locale = await _callback_locale(cq)
    mfa_token = cq.data.split(":", 1)[1] if ":" in cq.data else ""
    await cq.answer(msg("reporting", locale))

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        "/bot/tg-callbacks/mfa-report",
        {"chat_id": chat_id, "mfa_token": mfa_token},
    )

    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(cq, msg("security_reported_footer", locale))
    elif code == 404:
        await cq.answer(msg("account_not_linked_short", locale), show_alert=True)
    else:
        detail = data.get("detail", str(code))
        await cq.answer(msg("report_failed", locale, detail=detail), show_alert=True)


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

    locale = await _callback_locale(cq)
    sub_id = cq.data.split(":", 1)[1] if ":" in cq.data else ""
    if not sub_id:
        await cq.answer(msg("invalid_id", locale), show_alert=True)
        return

    await cq.answer(msg("sending_decision", locale))

    chat_id = cq.from_user.id
    code, data = await _signed_post(
        f"/bot/tg-callbacks/{module}/{sub_id}/decision",
        {"chat_id": chat_id, "decision": decision},
    )

    label_ok = msg(
        "decision_approved" if decision == "approve" else "decision_changes",
        locale,
    )
    if code == 200 and data.get("ok"):
        await _strip_kbd_and_append(
            cq, f"{label_ok}\n<i>{msg('decision_done', locale)}</i>"
        )
    elif code == 404:
        await cq.answer(msg("account_or_entity_missing", locale), show_alert=True)
    elif code == 403:
        await cq.answer(msg("action_forbidden", locale), show_alert=True)
    elif code == 409:
        detail = data.get("detail", str(code))
        await cq.answer(msg("action_conflict", locale, detail=detail), show_alert=True)
    else:
        detail = data.get("detail", str(code))
        await cq.answer(msg("action_failed", locale, detail=detail), show_alert=True)


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
    locale = await _callback_locale(cq)
    parts = cq.data.split(":", 2)
    if len(parts) != 3:
        await cq.answer(msg("invalid_callback", locale), show_alert=True); return
    _, ent_type, ent_id = parts

    _PENDING_REPLIES[cq.from_user.id] = {
        "entity_type": ent_type,
        "entity_id": ent_id,
        "expires_at": _time.time() + 600,
    }
    await cq.answer(msg("waiting_reply", locale))
    try:
        await cq.message.reply(msg("reply_prompt", locale))
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
