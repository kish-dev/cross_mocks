from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Отправить свой набор на проверку", callback_data="menu:submit_pack")
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


def admin_submission_review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Принять", callback_data=f"submission:approve:{submission_id}")
    kb.button(text="✏️ Нужны правки", callback_data=f"submission:changes:{submission_id}")
    kb.adjust(2)
    return kb.as_markup()
