import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.config import settings
from app.bot.middlewares.access import AccessMiddleware
from app.bot.routers import start


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(settings.BOT_TOKEN)
    redis = Redis.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=RedisStorage(redis=redis))

    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    dp.include_router(start.router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
