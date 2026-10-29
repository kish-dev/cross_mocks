import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from app.config import settings
from app.services.access import ALLOWED, get_membership_status


logger = logging.getLogger("tgmocks.access")

MEMBERSHIP_UNAVAILABLE_TEXT = (
    "Не удалось проверить участие в группе из-за ошибки Telegram. "
    "Попробуй /start ещё раз через минуту. Если ошибка повторяется, напиши Антону."
)
ACCESS_DENIED_TEXT = (
    "Доступ только для участников приватной группы.\n"
    "Если хочешь присоединиться к формату моков и менторства:\n"
    "https://storm-paneer-5a4.notion.site/Android-2ac8b91c3fe48155b0a0f098f865e092"
)
ACCESS_DENIED_ALERT = "Доступ только для участников приватной группы. Отправь /start, чтобы узнать подробнее."


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not getattr(event, "from_user", None):
            return await handler(event, data)

        # admin bypass for emergency access/debug
        if event.from_user.id in settings.admin_ids:
            return await handler(event, data)

        status = await get_membership_status(data["bot"], settings.PRIVATE_GROUP_ID, event.from_user.id)
        if status not in ALLOWED:
            check_failed = status.startswith("error:")
            if check_failed:
                logger.warning("membership_check_failed status=%s", status)
            else:
                logger.info("access_denied status=%s", status)

            if hasattr(event, "answer"):
                if isinstance(event, CallbackQuery):
                    text = MEMBERSHIP_UNAVAILABLE_TEXT if check_failed else ACCESS_DENIED_ALERT
                    await event.answer(text, show_alert=True)
                else:
                    text = MEMBERSHIP_UNAVAILABLE_TEXT if check_failed else ACCESS_DENIED_TEXT
                    await event.answer(text)
            return
        return await handler(event, data)
