import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from core.config import BotTokenConfig
from bot.handlers import router
from bot.group_handlers import group_router
from db.base import engine, Base
from db.models import User, Shift


logging.basicConfig(level=logging.INFO)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot = Bot(
        token=BotTokenConfig.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()


    dp.include_router(router)
    dp.include_router(group_router)



    await bot.set_my_commands(
    [BotCommand(command="status", description="Сменить статус: ночной / дневной")],
    scope=BotCommandScopeAllPrivateChats(),
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())