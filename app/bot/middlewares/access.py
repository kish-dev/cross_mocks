from aiogram import BaseMiddleware
from app.config import settings
from app.services.access import is_member, get_membership_status


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if not getattr(event, "from_user", None):
            return await handler(event, data)

        # admin bypass for emergency access/debug
        if event.from_user.id in settings.admin_ids:
            return await handler(event, data)

        ok = await is_member(data["bot"], settings.PRIVATE_GROUP_ID, event.from_user.id)
        if not ok:
            if hasattr(event, "answer"):
                status = await get_membership_status(data["bot"], settings.PRIVATE_GROUP_ID, event.from_user.id)
                await event.answer(
                    "Доступ только для участников приватной группы.\n"
                    f"debug: user_id={event.from_user.id}, group_id={settings.PRIVATE_GROUP_ID}, status={status}"
                )
            return
        return await handler(event, data)
