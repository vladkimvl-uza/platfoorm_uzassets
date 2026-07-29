"""uza-tg-bot entry point.

Runs concurrently:
- aiogram polling (incoming messages: /start, /status, etc)
- outbox worker (outgoing: SELECT FROM telegram_outbox WHERE pending → send)
"""
import asyncio
import logging
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault, MenuButtonCommands

import config
import db
import handlers
from callbacks import router as callbacks_router
from i18n import msg
import outbox_worker


logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("uza-bot.main")


def _commands(locale: str) -> list[BotCommand]:
    return [
        BotCommand(command="start", description=msg("cmd_start", locale)),
        BotCommand(command="menu", description=msg("cmd_menu", locale)),
        BotCommand(command="status", description=msg("cmd_status", locale)),
        BotCommand(command="queue", description=msg("cmd_queue", locale)),
        BotCommand(command="sessions", description=msg("cmd_sessions", locale)),
        BotCommand(command="unlink", description=msg("cmd_unlink", locale)),
        BotCommand(command="help", description=msg("cmd_help", locale)),
    ]


async def main() -> None:
    log.info("Starting UzAssets bot (username=%s, db=%s)",
             config.BOT_USERNAME,
             config.DATABASE_URL.split("@")[-1])

    # DB pool
    await db.init_pool()

    # aiogram setup — Phase A: HTML parse mode for premium message styling
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    log.info("Bot authenticated: @%s (id=%s)", me.username, me.id)

    # Phase A: register persistent menu commands shown via "/" in Telegram chat
    try:
        await bot.set_my_commands(
            commands=_commands("ru"),
            scope=BotCommandScopeDefault(),
        )
        for language_code, locale in (("ru", "ru"), ("uz", "uz-latn"), ("en", "en")):
            await bot.set_my_commands(
                commands=_commands(locale),
                scope=BotCommandScopeDefault(),
                language_code=language_code,
            )
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        log.info("Bot menu commands registered")
    except Exception:
        log.exception("Failed to register bot commands (non-fatal)")

    dp = Dispatcher()
    dp.include_router(handlers.router)
    dp.include_router(callbacks_router)

    # Graceful shutdown via signals
    stop_event = asyncio.Event()

    def _signal_handler(signum, _frame):
        log.info("Got signal %s, shutting down", signum)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):
            # Inside thread / not main thread — skip
            pass

    # Run polling + outbox worker concurrently
    worker_task = asyncio.create_task(outbox_worker.loop(bot), name="outbox_worker")
    polling_task = asyncio.create_task(dp.start_polling(bot, polling_timeout=30), name="aiogram_polling")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop_event")

    done, pending = await asyncio.wait(
        {worker_task, polling_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    log.info("Main loop completed (done=%s)", [t.get_name() for t in done])

    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    await bot.session.close()
    await db.close_pool()
    log.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted")
        sys.exit(0)
    except Exception:
        log.exception("Fatal error")
        sys.exit(1)
