from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from app.config import settings
from app.db.models import User, Session, SessionFeedback
from app.db.session import SessionLocal
from app.repositories.users import UsersRepo
from app.bot.keyboards.common import main_menu_keyboard, admin_role_keyboard

router = Router()

WELCOME = (
    "Привет! Я бот для парных мок-собеседований.\n\n"
    "Что я делаю:\n"
    "— помогаю найти пару для мок-собеса\n"
    "— фиксирую результаты и прогресс\n"
    "— собираю статистику по прохождениям и проведениям\n\n"
    "Выбери действие ниже ⤵️"
)


class AdminStatsFlow(StatesGroup):
    waiting_nickname = State()


@router.message(CommandStart())
async def start_cmd(message: Message):
    async with SessionLocal() as session:
        await UsersRepo().upsert(
            session,
            tg_user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        await session.commit()

    is_admin = message.from_user.id in settings.admin_ids
    await message.answer(WELCOME, reply_markup=main_menu_keyboard(is_admin=is_admin))


@router.callback_query(F.data == "menu:find_interviewer")
async def find_interviewer(callback: CallbackQuery):
    await callback.message.answer("Ок, поиск интервьюера. Следующий шаг: выбери трек (FSM в разработке).")
    await callback.answer()


@router.callback_query(F.data == "menu:find_student")
async def find_student(callback: CallbackQuery):
    await callback.message.answer("Ок, поиск ученика. Следующий шаг: выбери трек (FSM в разработке).")
    await callback.answer()


@router.callback_query(F.data == "menu:my_stats")
async def my_stats(callback: CallbackQuery):
    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.message.answer("Пока нет данных. Начни с /start и создай первую активность.")
            await callback.answer()
            return

        passed_count = (
            await session.execute(select(func.count(Session.id)).where(Session.student_id == db_user.id))
        ).scalar_one()
        conducted_count = (
            await session.execute(select(func.count(Session.id)).where(Session.interviewer_id == db_user.id))
        ).scalar_one()

        avg_as_student = (
            await session.execute(
                select(func.avg(SessionFeedback.score))
                .where(SessionFeedback.about_user_id == db_user.id, SessionFeedback.role_context == "interviewer_report")
            )
        ).scalar_one()
        avg_as_interviewer = (
            await session.execute(
                select(func.avg(SessionFeedback.score))
                .where(SessionFeedback.about_user_id == db_user.id, SessionFeedback.role_context == "student_report")
            )
        ).scalar_one()

    await callback.message.answer(
        "Твоя статистика:\n"
        f"— Проходил собесы: {passed_count}\n"
        f"— Проводил собесы: {conducted_count}\n"
        f"— Средняя оценка как собеседуемый: {round(avg_as_student, 2) if avg_as_student is not None else 'n/a'}\n"
        f"— Средняя оценка как собеседующий: {round(avg_as_interviewer, 2) if avg_as_interviewer is not None else 'n/a'}"
    )
    await callback.answer()


@router.callback_query(F.data == "menu:admin_stats")
async def admin_stats_entry(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return
    await state.set_state(AdminStatsFlow.waiting_nickname)
    await callback.message.answer("Введи @username пользователя (например @anton):")
    await callback.answer()


@router.message(AdminStatsFlow.waiting_nickname)
async def admin_stats_nickname(message: Message, state: FSMContext):
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return

    username = message.text.strip().lstrip("@").lower()
    if not username:
        await message.answer("Нужен username в формате @name")
        return

    await state.update_data(username=username)
    await message.answer("Выбери режим статистики:", reply_markup=admin_role_keyboard())


@router.callback_query(F.data.startswith("admin_role:"))
async def admin_stats_role(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    data = await state.get_data()
    username = data.get("username")
    if not username:
        await callback.message.answer("Сначала введи username через кнопку админ-статистики.")
        await callback.answer()
        return

    mode = callback.data.split(":", 1)[1]

    async with SessionLocal() as session:
        db_user = (
            await session.execute(
                select(User).where(func.lower(User.username) == username)
            )
        ).scalar_one_or_none()

        if not db_user:
            await callback.message.answer(f"Пользователь @{username} не найден в базе.")
            await callback.answer()
            return

        if mode == "student":
            cnt = (await session.execute(select(func.count(Session.id)).where(Session.student_id == db_user.id))).scalar_one()
            avg = (
                await session.execute(
                    select(func.avg(SessionFeedback.score)).where(
                        SessionFeedback.about_user_id == db_user.id,
                        SessionFeedback.role_context == "interviewer_report",
                    )
                )
            ).scalar_one()
            text = (
                f"Админ-статистика для @{username} (как собеседуемый):\n"
                f"— Кол-во прохождений: {cnt}\n"
                f"— Средняя оценка: {round(avg, 2) if avg is not None else 'n/a'}"
            )
        else:
            cnt = (await session.execute(select(func.count(Session.id)).where(Session.interviewer_id == db_user.id))).scalar_one()
            avg = (
                await session.execute(
                    select(func.avg(SessionFeedback.score)).where(
                        SessionFeedback.about_user_id == db_user.id,
                        SessionFeedback.role_context == "student_report",
                    )
                )
            ).scalar_one()
            text = (
                f"Админ-статистика для @{username} (как собеседующий):\n"
                f"— Кол-во проведений: {cnt}\n"
                f"— Средняя оценка от собеседуемых: {round(avg, 2) if avg is not None else 'n/a'}"
            )

    await state.clear()
    await callback.message.answer(text)
    await callback.answer()
