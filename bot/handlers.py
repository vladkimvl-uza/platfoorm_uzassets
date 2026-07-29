"""aiogram 3 message + command handlers for UzAssets bot (Phase A: HTML upgrade)."""
import logging
from html import escape as _esc

from aiogram import Router, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)

import config
import db
import formatter as fmt
from i18n import VALID_LOCALES, locale_from_telegram, msg, normalize_locale

log = logging.getLogger("uza-bot.handlers")
router = Router()


# ── Persistent reply-keyboard (2×2) shown after /start ───────────────────

def _locale(message: Message, user: dict | None = None) -> str:
    if user and user.get("ui_locale"):
        return normalize_locale(user["ui_locale"])
    language = message.from_user.language_code if message.from_user else None
    return locale_from_telegram(language)


def _persistent_kbd(locale: str = "ru") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"📋 {msg('menu_tasks', locale)}"),
             KeyboardButton(text=f"🛡 {msg('menu_moderation', locale)}")],
            [KeyboardButton(text=f"📊 {msg('menu_dashboard', locale)}"),
             KeyboardButton(text=f"⚙ {msg('menu_settings', locale)}")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=msg("menu_placeholder", locale),
    )


# Map persistent-keyboard label → platform deep-link path.
_MENU_KEYS: tuple[tuple[str, str, str], ...] = (
    ("📋", "menu_tasks", "/my/tasks"),
    ("🛡", "menu_moderation", "/admin/moderation"),
    ("📊", "menu_dashboard", "/dashboard"),
    ("⚙", "menu_settings", "/settings/notifications"),
)
_MENU_LINKS: dict[str, str] = {
    f"{icon} {msg(key, locale)}": path
    for locale in VALID_LOCALES
    for icon, key, path in _MENU_KEYS
}


# ── /start (with deep-link token = confirmation card) ────────────────────

@router.message(CommandStart(deep_link=True))
async def cmd_start_with_token(message: Message, command: CommandObject) -> None:
    """Pack 13.3: show a confirmation card with name/email/role before
    committing the link. Buttons «Это я» / «Это не я» finalize via callbacks.
    """
    token = (command.args or "").strip()
    if not token:
        return await cmd_start_plain(message)

    info = await db.lookup_user_by_link_token(token)
    if info is None:
        return await message.answer(fmt.fmt_link_token_invalid(_locale(message)))

    locale = normalize_locale(info.get("ui_locale"))

    full_name = _esc(info["full_name"])
    email     = _esc(info["email"])
    role      = _esc(info["role_label"])

    card_text = msg(
        "link_card", locale, name=full_name, email=email, role=role,
    )
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✓ {msg('confirm_me', locale, name=info['full_name'])}",
            callback_data=f"tglink:confirm:{token}",
        )],
        [InlineKeyboardButton(
            text=f"⚠ {msg('not_me', locale).removesuffix(' ⚠')}",
            callback_data=f"tglink:deny:{token}",
        )],
    ])
    await message.answer(card_text, reply_markup=kbd, disable_web_page_preview=True)


@router.message(CommandStart())
async def cmd_start_plain(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if user:
        locale = _locale(message, user)
        await message.answer(
            f"<b>UzAssets · {_esc(user['email'])}</b>\n\n"
            + msg("already_linked", locale),
            reply_markup=_persistent_kbd(locale),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(
            fmt.fmt_welcome_no_token(_locale(message)),
            disable_web_page_preview=True,
        )


# ── /menu ────────────────────────────────────────────────────────────────

@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(
            fmt.fmt_not_linked(_locale(message)), disable_web_page_preview=True,
        )
    locale = _locale(message, user)
    await message.answer(
        fmt.fmt_menu(locale),
        reply_markup=_persistent_kbd(locale),
        disable_web_page_preview=True,
    )


# ── /help ────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    await message.answer(
        fmt.fmt_help(_locale(message, user)), disable_web_page_preview=True,
    )


# ── /status ──────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(
            fmt.fmt_not_linked(_locale(message)), disable_web_page_preview=True,
        )
    locale = _locale(message, user)
    if not user.get("is_active"):
        return await message.answer(msg("account_disabled", locale))

    notifications = await db.get_recent_notifications(user["id"], limit=5)
    await message.answer(fmt.fmt_status(user["email"], notifications, locale),
                         disable_web_page_preview=True)


# ── /queue (permission-gated) ────────────────────────────────────────────

@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(
            fmt.fmt_not_linked(_locale(message)), disable_web_page_preview=True,
        )
    locale = _locale(message, user)

    has_mod_perm = await db.has_permission(user["id"], "moderation.review")
    if not has_mod_perm:
        return await message.answer(msg("moderation_permission", locale))

    items = await db.get_moderation_queue(limit=10)
    await message.answer(fmt.fmt_queue(items, locale), disable_web_page_preview=True)


# ── /sessions ────────────────────────────────────────────────────────────

@router.message(Command("sessions"))
async def cmd_sessions(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(
            fmt.fmt_not_linked(_locale(message)), disable_web_page_preview=True,
        )

    sessions = await db.get_user_sessions(user["id"])
    await message.answer(
        fmt.fmt_sessions(sessions, _locale(message, user)),
        disable_web_page_preview=True,
    )


# ── /unlink ──────────────────────────────────────────────────────────────

@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    locale = _locale(message, user)
    ok = await db.unlink_telegram_by_chat(message.from_user.id)
    if ok:
        log.info("Unlinked chat_id=%s", message.from_user.id)
        await message.answer(
            fmt.fmt_unlinked(locale),
            reply_markup=ReplyKeyboardRemove(),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(fmt.fmt_not_linked(locale), disable_web_page_preview=True)


# ── Persistent-keyboard button taps → deep-link proxy ────────────────────

@router.message(F.text.in_(_MENU_LINKS.keys()))
async def cmd_menu_proxy(message: Message) -> None:
    label = message.text or ""
    path  = _MENU_LINKS.get(label, "/")
    url   = f"{config.PLATFORM_URL.rstrip('/')}{path}"
    user = await db.find_user_by_chat_id(message.from_user.id)
    locale = _locale(message, user)
    await message.answer(
        f"<b>{_esc(label)}</b>\n\n"
        f"<a href=\"{_esc(url)}\">{_esc(url)}</a>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=msg("open_platform", locale), url=url)],
        ]),
        disable_web_page_preview=True,
    )


# ── /cancel — clear pending reply state ─────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    from callbacks import clear_pending_reply, get_pending_reply
    user = await db.find_user_by_chat_id(message.from_user.id)
    locale = _locale(message, user)
    if get_pending_reply(message.from_user.id):
        clear_pending_reply(message.from_user.id)
        await message.answer(f"<i>{msg('reply_cancelled', locale)}</i>")
    else:
        await message.answer(f"<i>{msg('nothing_to_cancel', locale)}</i>")


# ── Pending reply: next text message becomes a comment ──────────────────

@router.message(F.text)
async def cmd_pending_or_unknown(message: Message) -> None:
    """If user is in pending-reply state (after clicking «Ответить в чате»),
    post their next message as a comment back to the platform. Otherwise
    show the fallback help message."""
    from callbacks import get_pending_reply, clear_pending_reply, _signed_post

    pending = get_pending_reply(message.from_user.id) if message.from_user else None
    user = await db.find_user_by_chat_id(message.from_user.id) if message.from_user else None
    locale = _locale(message, user)
    if pending:
        ent_type = pending["entity_type"]
        ent_id = pending["entity_id"]
        body = (message.text or "").strip()
        if not body:
            await message.answer(msg("empty_reply", locale))
            return

        chat_id = message.from_user.id
        code, data = await _signed_post(
            "/bot/tg-callbacks/comment-from-tg",
            {"chat_id": chat_id, "entity_type": ent_type, "entity_id": ent_id, "body": body},
        )
        if code == 200 and data.get("ok"):
            clear_pending_reply(chat_id)
            url = f"{config.PLATFORM_URL.rstrip('/')}/{ent_type}s/{ent_id}"
            await message.answer(
                f"<b>✓ {msg('comment_sent', locale)}</b>\n\n"
                f"{msg('published_platform', locale)} "
                f"<a href=\"{_esc(url)}\">{msg('open_entity', locale, entity=_esc(ent_type))}</a>",
                disable_web_page_preview=True,
            )
        elif code == 403:
            await message.answer(msg("comment_forbidden", locale))
            clear_pending_reply(chat_id)
        else:
            detail = data.get("detail", "error")
            await message.answer(
                f"<i>{msg('send_failed', locale, detail=_esc(str(detail)))}</i>"
            )
        return

    # Fallback
    await message.answer(
        f"<i>{msg('unknown_command', locale)}</i>",
        disable_web_page_preview=True,
    )
