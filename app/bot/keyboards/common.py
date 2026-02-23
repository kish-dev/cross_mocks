from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🎯 Хочу пройти собес", callback_data="menu:find_interviewer")
    kb.button(text="🧑‍🏫 Хочу провести собес", callback_data="menu:find_student")
    kb.button(text="📊 Моя статистика", callback_data="menu:my_stats")
    if is_admin:
        kb.button(text="🛠 Админ: статистика по ученику", callback_data="menu:admin_stats")
    kb.adjust(1)
    return kb.as_markup()


def admin_role_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Собеседующий", callback_data="admin_role:interviewer")
    kb.button(text="Собеседуемый", callback_data="admin_role:student")
    kb.adjust(2)
    return kb.as_markup()
