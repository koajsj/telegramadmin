from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.app_context import AppContext
from bot.config import load_settings
from bot.database.session import create_engine, create_redis, create_session_factory, init_schema
from bot.handlers import ALL_ROUTERS


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def run_bot() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    redis = create_redis(settings)
    await init_schema(engine)

    keyword_files_dir = Path(__file__).resolve().parent.parent / "data"
    app_context = AppContext(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        keyword_files_dir=keyword_files_dir,
    )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    for router in ALL_ROUTERS:
        dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(bot, app_context=app_context)
    finally:
        await redis.aclose()
        await engine.dispose()
        await bot.session.close()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
