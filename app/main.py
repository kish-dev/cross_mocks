import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy import select

from app.config import settings
from app.bot.middlewares.access import AccessMiddleware
from app.bot.routers import start
from app.bot.keyboards.common import start_session_keyboard
from app.db.session import SessionLocal
from app.db.models import Session, User


logger = logging.getLogger("tgmocks.reminder")


async def reminder_worker(bot: Bot):
    start_nudged: set[int] = set()

    while True:
        try:
            now = datetime.utcnow()
            border = now + timedelta(minutes=15)
            async with SessionLocal() as session:
                # T-15 reminder
                rows = (
                    await session.execute(
                        select(Session).where(
                            Session.status == "scheduled",
                            Session.reminder_sent.is_(False),
                            Session.starts_at <= border,
                            Session.starts_at >= now - timedelta(minutes=1),
                        )
                    )
                ).scalars().all()

                for s in rows:
                    users = (
                        await session.execute(select(User).where(User.id.in_([s.student_id, s.interviewer_id])))
                    ).scalars().all()
                    for u in users:
                        try:
                            await bot.send_message(
                                u.tg_user_id,
                                "⏰ Напоминание: через 15 минут у вас собес.\n"
                                f"Время: {s.starts_at.strftime('%Y-%m-%d %H:%M')} MSK",
                                reply_markup=start_session_keyboard(s.id),
                            )
                            logger.info("sent_t15_reminder session_id=%s tg_user_id=%s", s.id, u.tg_user_id)
                        except Exception as e:
                            logger.warning("failed_t15_reminder session_id=%s tg_user_id=%s err=%s", s.id, u.tg_user_id, e)
                    s.reminder_sent = True

                # Start-time nudge if session wasn't started via button yet
                overdue = (
                    await session.execute(
                        select(Session).where(
                            Session.status == "scheduled",
                            Session.starts_at <= now,
                        )
                    )
                ).scalars().all()

                for s in overdue:
                    if s.id in start_nudged:
                        continue
                    users = (
                        await session.execute(select(User).where(User.id.in_([s.student_id, s.interviewer_id])))
                    ).scalars().all()
                    for u in users:
                        try:
                            await bot.send_message(
                                u.tg_user_id,
                                "🚨 Время собеса (MSK) уже наступило, но старт ещё не подтвержден.\n"
                                "Нажмите кнопку ниже, чтобы начать.",
                                reply_markup=start_session_keyboard(s.id),
                            )
                            logger.info("sent_start_nudge session_id=%s tg_user_id=%s", s.id, u.tg_user_id)
                        except Exception as e:
                            logger.warning("failed_start_nudge session_id=%s tg_user_id=%s err=%s", s.id, u.tg_user_id, e)
                    start_nudged.add(s.id)

                # cleanup memory set when session moved out of scheduled
                active_scheduled_ids = set(
                    (await session.execute(select(Session.id).where(Session.status == "scheduled"))).scalars().all()
                )
                start_nudged.intersection_update(active_scheduled_ids)

                await session.commit()
        except Exception:
            pass

        await asyncio.sleep(60)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(settings.BOT_TOKEN)
    redis = Redis.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=RedisStorage(redis=redis))

    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    dp.include_router(start.router)

    asyncio.create_task(reminder_worker(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
