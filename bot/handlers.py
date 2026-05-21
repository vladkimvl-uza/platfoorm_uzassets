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

log = logging.getLogger("uza-bot.handlers")
router = Router()


# ── Persistent reply-keyboard (2×2) shown after /start ───────────────────

def _persistent_kbd() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мои задачи"),    KeyboardButton(text="🛡 На модерации")],
            [KeyboardButton(text="📊 Дашборд"),        KeyboardButton(text="⚙ Настройки")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие или используйте /menu",
    )


# Map persistent-keyboard label → platform deep-link path.
_MENU_LINKS: dict[str, str] = {
    "📋 Мои задачи":    "/my/tasks",
    "🛡 На модерации": "/admin/moderation",
    "📊 Дашборд":       "/dashboard",
    "⚙ Настройки":     "/settings/notifications",
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
        return await message.answer(fmt.fmt_link_token_invalid())

    full_name = _esc(info["full_name"])
    email     = _esc(info["email"])
    role      = _esc(info["role_label"])

    card_text = (
        "<b>UzAssets · Подтверждение привязки</b>\n"
        "\n"
        "Подтвердите, что этот Telegram принадлежит вам:\n"
        "\n"
        f"  Имя:   <b>{full_name}</b>\n"
        f"  Email: <code>{email}</code>\n"
        f"  Роль:  <i>{role}</i>\n"
        "\n"
        "<i>Если это не вы — нажмите «Это не я» и сообщите администратору.</i>"
    )
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✓ Это я, {info['full_name']}",
            callback_data=f"tglink:confirm:{token}",
        )],
        [InlineKeyboardButton(
            text="⚠ Это не я",
            callback_data=f"tglink:deny:{token}",
        )],
    ])
    await message.answer(card_text, reply_markup=kbd, disable_web_page_preview=True)


@router.message(CommandStart())
async def cmd_start_plain(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if user:
        await message.answer(
            f"<b>UzAssets · {_esc(user['email'])}</b>\n\n"
            "Этот чат уже привязан. Откройте /menu или /help.",
            reply_markup=_persistent_kbd(),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(fmt.fmt_welcome_no_token(), disable_web_page_preview=True)


# ── /menu ────────────────────────────────────────────────────────────────

@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked(), disable_web_page_preview=True)
    await message.answer(
        fmt.fmt_menu(),
        reply_markup=_persistent_kbd(),
        disable_web_page_preview=True,
    )


# ── /help ────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(fmt.fmt_help(), disable_web_page_preview=True)


# ── /status ──────────────────────────────────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked(), disable_web_page_preview=True)
    if not user.get("is_active"):
        return await message.answer(
            "<b>UzAssets · Аккаунт отключён</b>\n\n"
            "Ваш аккаунт деактивирован администратором."
        )

    notifications = await db.get_recent_notifications(user["id"], limit=5)
    await message.answer(fmt.fmt_status(user["email"], notifications),
                         disable_web_page_preview=True)


# ── /queue (permission-gated) ────────────────────────────────────────────

@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked(), disable_web_page_preview=True)

    has_mod_perm = await db.has_permission(user["id"], "moderation.review")
    if not has_mod_perm:
        return await message.answer(
            "<b>UzAssets · Недостаточно прав</b>\n\n"
            "Для просмотра очереди модерации требуется право <code>moderation.review</code>."
        )

    items = await db.get_moderation_queue(limit=10)
    await message.answer(fmt.fmt_queue(items), disable_web_page_preview=True)


# ── /sessions ────────────────────────────────────────────────────────────

@router.message(Command("sessions"))
async def cmd_sessions(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked(), disable_web_page_preview=True)

    sessions = await db.get_user_sessions(user["id"])
    await message.answer(fmt.fmt_sessions(sessions), disable_web_page_preview=True)


# ── /unlink ──────────────────────────────────────────────────────────────

@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    ok = await db.unlink_telegram_by_chat(message.from_user.id)
    if ok:
        log.info("Unlinked chat_id=%s", message.from_user.id)
        await message.answer(
            fmt.fmt_unlinked(),
            reply_markup=ReplyKeyboardRemove(),
            disable_web_page_preview=True,
        )
    else:
        await message.answer(fmt.fmt_not_linked(), disable_web_page_preview=True)


# ── Persistent-keyboard button taps → deep-link proxy ────────────────────

@router.message(F.text.in_(_MENU_LINKS.keys()))
async def cmd_menu_proxy(message: Message) -> None:
    label = message.text or ""
    path  = _MENU_LINKS.get(label, "/")
    url   = f"{config.PLATFORM_URL.rstrip('/')}{path}"
    await message.answer(
        f"<b>{_esc(label)}</b>\n\n"
        f"<a href=\"{_esc(url)}\">{_esc(url)}</a>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть в платформе →", url=url)],
        ]),
        disable_web_page_preview=True,
    )


# ── /cancel — clear pending reply state ─────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    from callbacks import clear_pending_reply, get_pending_reply
    if get_pending_reply(message.from_user.id):
        clear_pending_reply(message.from_user.id)
        await message.answer("<i>Ответ отменён.</i>")
    else:
        await message.answer("<i>Нечего отменять.</i>")


# ── Pending reply: next text message becomes a comment ──────────────────

@router.message(F.text)
async def cmd_pending_or_unknown(message: Message) -> None:
    """If user is in pending-reply state (after clicking «Ответить в чате»),
    post their next message as a comment back to the platform. Otherwise
    show the fallback help message."""
    from callbacks import get_pending_reply, clear_pending_reply, _signed_post

    pending = get_pending_reply(message.from_user.id) if message.from_user else None
    if pending:
        ent_type = pending["entity_type"]
        ent_id = pending["entity_id"]
        body = (message.text or "").strip()
        if not body:
            await message.answer("Пустой ответ не отправлен. Напишите текст или /cancel")
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
                f"<b>✓ Комментарий отправлен</b>\n\n"
                f"Опубликован на платформе. "
                f"<a href=\"{_esc(url)}\">Открыть {ent_type} →</a>",
                disable_web_page_preview=True,
            )
        elif code == 403:
            await message.answer("Нет прав на комментирование. Ответ не сохранён.")
            clear_pending_reply(chat_id)
        else:
            detail = data.get("detail", "ошибка")
            await message.answer(f"<i>Не удалось отправить:</i> {_esc(str(detail))}\n\nПопробуй ещё или /cancel")
        return

    # Fallback
    await message.answer(
        "<i>Неизвестная команда.</i> Используйте /menu или /help.",
        disable_web_page_preview=True,
    )
