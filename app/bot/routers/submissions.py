import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards.common import admin_submission_review_keyboard, track_keyboard
from app.bot.routers.shared import TRACK_LABELS, continue_menu_for_user, continue_message_text
from app.config import settings
from app.db.models import CandidateSet, User
from app.db.session import SessionLocal
from app.repositories.users import UsersRepo

router = Router()


class SubmissionFlow(StatesGroup):
    waiting_track = State()
    waiting_title = State()
    waiting_questions = State()


class AdminSubmissionFlow(StatesGroup):
    waiting_comment = State()


@router.callback_query(F.data == "menu:submit_pack")
async def submit_pack_entry(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SubmissionFlow.waiting_track)
    await callback.message.answer("Выбери тип собеса для набора:", reply_markup=track_keyboard("submit_track"))
    await callback.answer()


@router.callback_query(F.data.startswith("submit_track:"))
async def submit_track_pick(callback: CallbackQuery, state: FSMContext):
    track = callback.data.split(":", 1)[1]
    await state.update_data(track=track)
    await state.set_state(SubmissionFlow.waiting_title)

    title_example = {
        "theory": "theory: Android Core #1",
        "sysdesign": "system-design: URL Shortener #1",
        "livecoding": "livecoding: Two Sum + LRU #1",
        "final": "final: self-intro + project deep-dive #1",
    }.get(track, "topic: your-set-name #1")

    await callback.message.answer(
        "Ок. Теперь пришли название этого набора.\n"
        f"Пример для {TRACK_LABELS.get(track, track)}: {title_example}"
    )
    await callback.answer()


@router.message(SubmissionFlow.waiting_title)
async def submit_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Название не может быть пустым.")
        return
    await state.update_data(title=title)
    await state.set_state(SubmissionFlow.waiting_questions)
    await message.answer("Теперь пришли ОДНИМ сообщением вопросы (или ссылку на них).")


@router.message(SubmissionFlow.waiting_questions)
async def submit_pack_content(message: Message, state: FSMContext):
    questions_text = (message.text or message.caption or "").strip()
    if not questions_text:
        await message.answer("Нужно отправить текст или ссылку одним сообщением.")
        return

    data = await state.get_data()
    track = data.get("track")
    title = data.get("title")

    async with SessionLocal() as session:
        db_user = await UsersRepo().upsert(
            session,
            tg_user_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )
        set_item = CandidateSet(
            owner_user_id=db_user.id,
            track_code=track,
            title=title,
            questions_text=questions_text,
            status="pending",
        )
        session.add(set_item)
        await session.commit()
        await session.refresh(set_item)

    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                "Вам на проверку прилетели вопросы для собеса.\n\n"
                f"От: @{message.from_user.username or 'no_username'} (id={message.from_user.id})\n"
                f"Тип: {TRACK_LABELS.get(track, track)}\n"
                f"Набор: {title}\n"
                f"set_id={set_item.id}\n\n"
                f"Вопросы:\n{questions_text}",
                reply_markup=admin_submission_review_keyboard(set_item.id),
            )
        except Exception:
            pass

    await state.clear()
    await message.answer("Отправил набор на проверку админу ✅")


@router.message(StateFilter(None), F.reply_to_message)
async def resubmit_via_reply(message: Message, state: FSMContext):
    reply_text = ((message.reply_to_message.text or "") + "\n" + (message.reply_to_message.caption or "")).strip()
    m = re.search(r"set_id=(\d+)", reply_text)

    content = (message.text or message.caption or "").strip()
    if not content:
        await message.answer("Отправь исправленный набор текстом или ссылкой одним сообщением.")
        return

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not db_user:
            await message.answer("Сначала нажми /start")
            return

        set_item = None
        if m:
            set_id = int(m.group(1))
            set_item = (
                await session.execute(
                    select(CandidateSet).where(CandidateSet.id == set_id, CandidateSet.owner_user_id == db_user.id)
                )
            ).scalar_one_or_none()

        if not set_item:
            set_item = (
                await session.execute(
                    select(CandidateSet)
                    .where(CandidateSet.owner_user_id == db_user.id, CandidateSet.status == "changes_requested")
                    .order_by(CandidateSet.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if not set_item:
            await message.answer(
                "Не нашёл набор в статусе правок.\n"
                "Ответь на сообщение бота с правками или отправь обычным сообщением исправленный набор."
            )
            return

        set_item.questions_text = content
        set_item.status = "pending"
        set_item.admin_comment = None
        await session.commit()

    delivered = 0
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                "Повторная отправка набора после правок 📌\n\n"
                f"От: @{message.from_user.username or 'no_username'} (id={message.from_user.id})\n"
                f"Тип: {TRACK_LABELS.get(set_item.track_code, set_item.track_code)}\n"
                f"Набор: {set_item.title}\n"
                f"set_id={set_item.id}\n\n"
                f"Обновлённые вопросы:\n{content}",
                reply_markup=admin_submission_review_keyboard(set_item.id),
            )
            delivered += 1
        except Exception:
            continue

    if delivered == 0:
        await message.answer("Не удалось доставить админу. Проверь ADMIN_TG_IDS в .env")
        return

    await message.answer("Исправления отправлены админу на повторную проверку ✅")


@router.callback_query(F.data.startswith("set_submission:approve:"))
async def admin_submission_approve(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    submission_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        submission = (await session.execute(select(CandidateSet).where(CandidateSet.id == submission_id))).scalar_one_or_none()
        if not submission:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        submission.status = "approved"
        submission.admin_comment = "Принято"
        await session.commit()

        student = (await session.execute(select(User).where(User.id == submission.owner_user_id))).scalar_one_or_none()

    if student:
        await callback.bot.send_message(
            student.tg_user_id,
            f"Твой набор '{submission.title}' ({TRACK_LABELS.get(submission.track_code, submission.track_code)}) принят ✅"
        )
        await callback.bot.send_message(
            student.tg_user_id,
            continue_message_text(),
            reply_markup=continue_menu_for_user(student.tg_user_id),
        )

    await callback.message.answer(f"set_id={submission_id} принят ✅")
    await callback.answer()


@router.callback_query(F.data.startswith("set_submission:changes:"))
async def admin_submission_changes(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    submission_id = int(callback.data.split(":")[-1])
    await state.set_state(AdminSubmissionFlow.waiting_comment)
    await state.update_data(submission_id=submission_id)
    await callback.message.answer(
        f"Введи текст правок для set_id={submission_id}.\n"
        "Статус останется на проверке (changes_requested)."
    )
    await callback.answer()


@router.message(AdminSubmissionFlow.waiting_comment)
async def admin_submission_comment(message: Message, state: FSMContext):
    if message.from_user.id not in settings.admin_ids:
        await state.clear()
        return

    comment = (message.text or "").strip()
    if not comment:
        await message.answer("Нужен текст правок.")
        return

    data = await state.get_data()
    submission_id = data.get("submission_id")
    if not submission_id:
        await state.clear()
        await message.answer("Сессия правок потерялась, начни заново.")
        return

    async with SessionLocal() as session:
        submission = (await session.execute(select(CandidateSet).where(CandidateSet.id == submission_id))).scalar_one_or_none()
        if not submission:
            await state.clear()
            await message.answer("Заявка не найдена.")
            return

        submission.status = "changes_requested"
        submission.admin_comment = comment
        await session.commit()

        student = (await session.execute(select(User).where(User.id == submission.owner_user_id))).scalar_one_or_none()

    if student:
        await message.bot.send_message(
            student.tg_user_id,
            "По твоему набору нужны правки ✏️\n"
            f"set_id={submission_id}\n"
            f"Комментарий админа:\n{comment}\n\n"
            "Отправь исправленный набор одним сообщением (reply-ответом или обычным сообщением в чат), и я отправлю его на повторную проверку админу."
        )

    await state.clear()
    await message.answer(f"Отправил правки ученику по set_id={submission_id}.")


@router.message()
async def auto_resubmit_latest_changes(message: Message, state: FSMContext):
    if not message.text and not message.caption:
        return
    if (message.text or "").startswith("/"):
        return

    current_state = await state.get_state()
    if current_state is not None:
        return

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not db_user:
            return

        set_item = (
            await session.execute(
                select(CandidateSet)
                .where(CandidateSet.owner_user_id == db_user.id, CandidateSet.status == "changes_requested")
                .order_by(CandidateSet.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if not set_item:
            return

        content = (message.text or message.caption or "").strip()
        if not content:
            return

        set_item.questions_text = content
        set_item.status = "pending"
        set_item.admin_comment = None
        await session.commit()

    delivered = 0
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                "Повторная отправка набора после правок 📌\n\n"
                f"От: @{message.from_user.username or 'no_username'} (id={message.from_user.id})\n"
                f"Тип: {TRACK_LABELS.get(set_item.track_code, set_item.track_code)}\n"
                f"Набор: {set_item.title}\n"
                f"set_id={set_item.id}\n\n"
                f"Обновлённые вопросы:\n{content}",
                reply_markup=admin_submission_review_keyboard(set_item.id),
            )
            delivered += 1
        except Exception:
            continue

    if delivered > 0:
        await message.answer("Исправления автоматически отправлены админу на повторную проверку ✅")
    else:
        await message.answer("Не удалось доставить админу. Проверь ADMIN_TG_IDS в .env")
