from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

ALLOWED = {"member", "administrator", "creator"}


async def is_member(bot: Bot, private_group_id: int, tg_user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(private_group_id, tg_user_id)
        return member.status in ALLOWED
    except TelegramBadRequest:
        return False
