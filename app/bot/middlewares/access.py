from aiogram import BaseMiddleware
from app.config import settings
from app.services.access import is_member


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not getattr(event, "from_user", None):
            return await handler(event, data)

        ok = await is_member(data["bot"], settings.PRIVATE_GROUP_ID, event.from_user.id)
        if not ok:
            if hasattr(event, "answer"):
                await event.answer("Доступ только для участников приватной группы.")
            return
        return await handler(event, data)
