import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy import select

from app.config import settings
from app.bot.middlewares.access import AccessMiddleware
from app.bot.routers import admin_stats, evaluations, proposals, sessions, start, stats, submissions
from app.bot.keyboards.common import start_session_keyboard
from app.db.session import SessionLocal
from app.db.models import Session, User
from app.services.delivery_queue import load_all, replace_all
from app.services.review_guards import (
    build_pending_review_reminder_text,
    get_pending_interviewer_reviews,
)
from app.utils.time import utcnow


logger = logging.getLogger("tgmocks.reminder")


async def reminder_worker(bot: Bot):
    start_nudged: set[int] = set()
    review_reminder_sent_at: dict[tuple[int, int], datetime] = {}

    while True:
        try:
            now = utcnow()
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

                pending_reviews = await get_pending_interviewer_reviews(session, now=now)
                active_review_keys: set[tuple[int, int]] = set()
                for item in pending_reviews:
                    key = (item.session_id, item.interviewer_tg_user_id)
                    active_review_keys.add(key)
                    last_sent_at = review_reminder_sent_at.get(key)
                    if last_sent_at and (now - last_sent_at) < timedelta(minutes=10):
                        continue
                    try:
                        await bot.send_message(
                            item.interviewer_tg_user_id,
                            build_pending_review_reminder_text(item),
                        )
                        logger.info(
                            "sent_review_reminder session_id=%s interviewer_tg_user_id=%s",
                            item.session_id,
                            item.interviewer_tg_user_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "failed_review_reminder session_id=%s interviewer_tg_user_id=%s err=%s",
                            item.session_id,
                            item.interviewer_tg_user_id,
                            e,
                        )
                    review_reminder_sent_at[key] = now

                stale_review_keys = [key for key in review_reminder_sent_at if key not in active_review_keys]
                for key in stale_review_keys:
                    review_reminder_sent_at.pop(key, None)

                await session.commit()
        except Exception:
            logger.exception("reminder_worker_error")

        await asyncio.sleep(60)


async def delivery_retry_worker(bot: Bot):
    while True:
        try:
            queued = load_all()
            if queued:
                remain = []
                for item in queued:
                    try:
                        await bot.send_message(item["tg_user_id"], item["text"])
                        logger.info("delivery_retry_ok tg_user_id=%s", item["tg_user_id"])
                    except Exception as e:
                        logger.warning("delivery_retry_fail tg_user_id=%s err=%s", item.get("tg_user_id"), e)
                        remain.append(item)
                replace_all(remain)
        except Exception as e:
            logger.warning("delivery_retry_worker_error err=%s", e)

        await asyncio.sleep(30)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    bot = Bot(settings.BOT_TOKEN)
    redis = Redis.from_url(settings.REDIS_URL)
    dp = Dispatcher(storage=RedisStorage(redis=redis))

    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    dp.include_router(start.router)
    dp.include_router(proposals.router)
    dp.include_router(sessions.router)
    dp.include_router(evaluations.router)
    dp.include_router(admin_stats.router)
    dp.include_router(stats.router)
    dp.include_router(submissions.router)

    asyncio.create_task(reminder_worker(bot))
    asyncio.create_task(delivery_retry_worker(bot))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
