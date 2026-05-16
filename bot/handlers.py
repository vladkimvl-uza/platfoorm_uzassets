"""aiogram 3 message + command handlers for UzAssets bot."""
import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

import db
import formatter as fmt

log = logging.getLogger("uza-bot.handlers")
router = Router()


# ── /start ────────────────────────────────────────────────────────────────

@router.message(CommandStart(deep_link=True))
async def cmd_start_with_token(message: Message, command: CommandObject) -> None:
    """Pack 13.3: show a confirmation card with name/email/role before
    committing the link. Buttons "Это я" / "Это не я" finalize via callbacks.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    token = (command.args or "").strip()
    if not token:
        return await cmd_start_plain(message)

    info = await db.lookup_user_by_link_token(token)
    if info is None:
        return await message.answer(fmt.fmt_link_token_invalid())

    card_text = (
        f"[UzAssets · подтверждение привязки]
"
        f"
"
        f"Подтвердите, что этот Telegram принадлежит вам:
"
        f"
"
        f"  Имя:   {info['full_name']}
"
        f"  Email: {info['email']}
"
        f"  Роль:  {info['role_label']}
"
        f"
"
        f"Если это не вы — нажмите «Это не я» и сообщите администратору."
    )
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✓ Это я, {info['full_name']}",
            callback_data=f"tglink:confirm:{token}",
        )],
        [InlineKeyboardButton(
            text="Это не я",
            callback_data=f"tglink:deny:{token}",
        )],
    ])
    await message.answer(card_text, reply_markup=kbd)


@router.message(CommandStart())
async def cmd_start_plain(message: Message) -> None:
    # If user is already linked, show their status instead of welcome
    user = await db.find_user_by_chat_id(message.from_user.id)
    if user:
        await message.answer(
            f"[UzAssets · {user['email']}]\n\n"
            "Этот чат уже привязан. Используйте /help для списка команд."
        )
    else:
        await message.answer(fmt.fmt_welcome_no_token())


# ── /help ─────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(fmt.fmt_help())


# ── /status — last unread notifications ───────────────────────────────────

@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked())
    if not user.get("is_active"):
        return await message.answer("[UzAssets · аккаунт отключён]\n\nВаш аккаунт деактивирован администратором.")

    notifications = await db.get_recent_notifications(user["id"], limit=5)
    await message.answer(fmt.fmt_status(user["email"], notifications))


# ── /queue — moderation (permission-gated) ────────────────────────────────

@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked())

    has_mod_perm = await db.has_permission(user["id"], "moderation.review")
    if not has_mod_perm:
        return await message.answer(
            "[UzAssets · недостаточно прав]\n\n"
            "Для просмотра очереди модерации требуется право moderation.review."
        )

    items = await db.get_moderation_queue(limit=10)
    await message.answer(fmt.fmt_queue(items))


# ── /sessions — list active sessions ──────────────────────────────────────

@router.message(Command("sessions"))
async def cmd_sessions(message: Message) -> None:
    user = await db.find_user_by_chat_id(message.from_user.id)
    if not user:
        return await message.answer(fmt.fmt_not_linked())

    sessions = await db.get_user_sessions(user["id"])
    await message.answer(fmt.fmt_sessions(sessions))


# ── /unlink ───────────────────────────────────────────────────────────────

@router.message(Command("unlink"))
async def cmd_unlink(message: Message) -> None:
    ok = await db.unlink_telegram_by_chat(message.from_user.id)
    if ok:
        log.info("Unlinked chat_id=%s", message.from_user.id)
        await message.answer(fmt.fmt_unlinked())
    else:
        await message.answer(fmt.fmt_not_linked())


# ── Fallback for any other text ───────────────────────────────────────────

@router.message(F.text)
async def cmd_unknown(message: Message) -> None:
    await message.answer("Неизвестная команда. Используйте /help.")
