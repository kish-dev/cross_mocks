from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

ALLOWED = {"member", "administrator", "creator"}


async def get_membership_status(bot: Bot, private_group_id: int, tg_user_id: int) -> str:
    try:
        member = await bot.get_chat_member(private_group_id, tg_user_id)
        return str(member.status)
    except TelegramAPIError as e:
        return f"error:{e.__class__.__name__}"


async def is_member(bot: Bot, private_group_id: int, tg_user_id: int) -> bool:
    status = await get_membership_status(bot, private_group_id, tg_user_id)
    return status in ALLOWED
