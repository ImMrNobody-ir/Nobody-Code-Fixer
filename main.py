import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import load_settings
from db.database import Database
from handlers import admin, code, menu, payment, saved
from middlewares import AccessMiddleware
from services.llm import GeminiClient

COMMANDS = [
    BotCommand(command="start", description="شروع و منوی اصلی"),
    BotCommand(command="help", description="راهنما"),
    BotCommand(command="account", description="حساب و سهمیه من"),
    BotCommand(command="saved", description="راه‌حل‌های ذخیره‌شده"),
    BotCommand(command="clear", description="پاک‌کردن حافظه گفتگو"),
]


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()

    db = Database(settings.db_path)
    await db.connect()

    llm = GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        base_url=settings.gemini_base_url,
        proxy=settings.proxy_url,
    )

    session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else AiohttpSession()
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage(), db=db, llm=llm, settings=settings)
    middleware = AccessMiddleware()
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)

    # Order matters: specific handlers first, the catch-all text/photo/file handler last.
    dp.include_routers(admin.router, payment.router, menu.router, saved.router, code.router)

    try:
        await bot.set_my_commands(COMMANDS)
        me = await bot.get_me()
        logging.info("Bot started as @%s (model: %s)", me.username, settings.gemini_model)
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await llm.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
