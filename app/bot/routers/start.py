import re

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from app.config import settings
from app.db.models import User, Session, SessionFeedback, CandidateSet, QuickEvaluation
from app.db.session import SessionLocal
from app.repositories.users import UsersRepo
from app.bot.keyboards.common import (
    main_menu_keyboard,
    admin_role_keyboard,
    admin_submission_review_keyboard,
    track_keyboard,
    evaluation_keyboard,
)

router = Router()

TRACK_LABELS = {
    "theory": "theory",
    "sysdesign": "system-design",
    "livecoding": "livecoding",
    "final": "final",
}

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


class SubmissionFlow(StatesGroup):
    waiting_track = State()
    waiting_title = State()
    waiting_questions = State()


class AdminSubmissionFlow(StatesGroup):
    waiting_comment = State()


class EvaluationFlow(StatesGroup):
    waiting_candidate_pick = State()
    waiting_candidate_username = State()
    waiting_scores = State()
    waiting_comment = State()


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
    await callback.message.answer("Ок. Теперь пришли название этого набора (например: 'Теория #1 Android Core').")
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


@router.message(F.reply_to_message)
async def resubmit_via_reply(message: Message, state: FSMContext):
    # one-click flow: user replies to admin changes message with updated set content
    current_state = await state.get_state()
    if current_state is not None:
        return

    reply_text = ((message.reply_to_message.text or "") + "\n" + (message.reply_to_message.caption or "")).strip()
    m = re.search(r"set_id=(\d+)", reply_text)
    if not m:
        return

    content = (message.text or message.caption or "").strip()
    if not content:
        await message.answer("Отправь исправленный набор текстом или ссылкой одним сообщением.")
        return

    set_id = int(m.group(1))

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not db_user:
            await message.answer("Сначала нажми /start")
            return

        set_item = (
            await session.execute(
                select(CandidateSet).where(CandidateSet.id == set_id, CandidateSet.owner_user_id == db_user.id)
            )
        ).scalar_one_or_none()

        if not set_item:
            await message.answer("Не нашёл твой набор для этого set_id. Проверь, что отвечаешь на корректное сообщение.")
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


@router.callback_query(F.data == "menu:find_interviewer")
async def find_interviewer(callback: CallbackQuery):
    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.message.answer("Сначала нажми /start")
            await callback.answer()
            return

        approved_count = (
            await session.execute(
                select(func.count(CandidateSet.id)).where(
                    CandidateSet.owner_user_id == db_user.id,
                    CandidateSet.status == "approved",
                )
            )
        ).scalar_one()

    if approved_count < 1:
        await callback.message.answer(
            "Чтобы пройти собес, сначала отправь минимум 1 свой набор на проверку админа.\n"
            "Нажми кнопку: «📝 Отправить свой набор на проверку»."
        )
        await callback.answer()
        return

    await callback.message.answer("Ок, ты можешь проходить собес. Подбор пары/расписания сейчас в следующем шаге разработки.")
    await callback.answer()


@router.callback_query(F.data == "menu:find_student")
async def find_student(callback: CallbackQuery):
    await callback.message.answer("Выбери трек собеса:", reply_markup=track_keyboard("conduct_track"))
    await callback.answer()


@router.callback_query(F.data.startswith("conduct_track:"))
async def conduct_track(callback: CallbackQuery):
    track = callback.data.split(":", 1)[1]

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(CandidateSet.id, CandidateSet.title)
                .where(CandidateSet.track_code == track, CandidateSet.status == "approved")
                .order_by(CandidateSet.created_at.desc())
                .limit(20)
            )
        ).all()

    if not rows:
        await callback.message.answer("Пока нет одобренных наборов по этому треку.")
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for set_id, title in rows:
        kb.button(text=title[:60], callback_data=f"conduct_set:{set_id}")
    kb.adjust(1)

    await callback.message.answer("Выбери набор вопросов:", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("conduct_set:"))
async def conduct_set(callback: CallbackQuery):
    set_id = int(callback.data.split(":", 1)[1])

    async with SessionLocal() as session:
        set_item = (await session.execute(select(CandidateSet).where(CandidateSet.id == set_id))).scalar_one_or_none()

    if not set_item:
        await callback.message.answer("Набор не найден.")
        await callback.answer()
        return

    await callback.message.answer(
        f"Набор: {set_item.title}\n"
        f"Трек: {TRACK_LABELS.get(set_item.track_code, set_item.track_code)}\n\n"
        "Вопросы для интервьюера:\n"
        f"{set_item.questions_text}",
        reply_markup=evaluation_keyboard(set_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("eval:start:"))
async def eval_start(callback: CallbackQuery, state: FSMContext):
    set_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        set_item = (await session.execute(select(CandidateSet).where(CandidateSet.id == set_id))).scalar_one_or_none()
        users = (
            await session.execute(
                select(User)
                .where(User.tg_user_id != callback.from_user.id, User.username.is_not(None), User.is_active.is_(True))
                .order_by(User.created_at.desc())
                .limit(15)
            )
        ).scalars().all()

    if not set_item:
        await callback.message.answer("Набор не найден")
        await callback.answer()
        return

    await state.update_data(set_id=set_id, track_code=set_item.track_code)
    await state.set_state(EvaluationFlow.waiting_candidate_pick)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for u in users:
        kb.button(text=f"@{u.username}", callback_data=f"eval:candidate:{u.username}")
    kb.button(text="Ввести вручную", callback_data="eval:candidate:manual")
    kb.adjust(1)

    await callback.message.answer("Выбери кандидата из списка или введи вручную:", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("eval:candidate:"))
async def eval_candidate_pick(callback: CallbackQuery, state: FSMContext):
    picked = callback.data.split(":", 2)[2]
    if picked == "manual":
        await state.set_state(EvaluationFlow.waiting_candidate_username)
        await callback.message.answer("Введи username кандидата в формате @username")
        await callback.answer()
        return

    username = picked.strip().lstrip("@").lower()
    await _evaluation_prompt_scores(callback.message, state, username)
    await callback.answer()


@router.message(EvaluationFlow.waiting_candidate_username)
async def eval_username(message: Message, state: FSMContext):
    username = (message.text or "").strip().lstrip("@").lower()
    if not username:
        await message.answer("Нужен @username")
        return

    await _evaluation_prompt_scores(message, state, username)


async def _evaluation_prompt_scores(target_message: Message, state: FSMContext, username: str):
    data = await state.get_data()
    track = data.get("track_code")

    if track == "theory":
        hint = (
            "Шкала 0-3. Пришли 3 числа через пробел:\n"
            "1) понимание темы\n2) применение на практике\n3) защита ответа\n"
            "Пример: 2 1 2\n"
            "Важно: без примера из опыта максимум 2."
        )
    elif track == "livecoding":
        hint = (
            "Шкала 0-3. Пришли 3 числа через пробел:\n"
            "1) старт решения\n2) рабочесть решения\n3) проговаривание хода мыслей\n"
            "Пример: 2 2 1"
        )
    elif track == "sysdesign":
        hint = (
            "Шкала 0-3. Пришли 4 значения:\n"
            "1) структура\n2) аргументация компромиссов\n3) целостность\n4) задавал ли уточняющие вопросы (yes/no)\n"
            "Пример: 2 2 1 yes\n"
            "Если без уточняющих вопросов — минус 1 к итогу."
        )
    else:  # final
        hint = (
            "Финалка (новая шкала 0-3). Пришли 2 числа:\n"
            "1) как рассказал о себе (структура/уверенность)\n"
            "2) глубина пояснений по опыту\n"
            "Пример: 2 3"
        )

    await state.update_data(candidate_username=username)
    await state.set_state(EvaluationFlow.waiting_scores)
    await target_message.answer(hint)


@router.message(EvaluationFlow.waiting_scores)
async def eval_scores(message: Message, state: FSMContext):
    raw = (message.text or "").strip().lower()
    data = await state.get_data()
    track = data.get("track_code")

    parts = raw.replace(",", " ").split()

    try:
        if track in {"theory", "livecoding"}:
            if len(parts) != 3:
                raise ValueError
            nums = [int(x) for x in parts]
            if any(x < 0 or x > 3 for x in nums):
                raise ValueError
            final_avg = sum(nums) / 3
            rubric = f"scores={nums}"
        elif track == "sysdesign":
            if len(parts) != 4:
                raise ValueError
            nums = [int(x) for x in parts[:3]]
            if any(x < 0 or x > 3 for x in nums):
                raise ValueError
            asked = parts[3] in {"yes", "y", "да"}
            final_avg = sum(nums) / 3
            if not asked:
                final_avg = max(0.0, final_avg - 1.0)
            rubric = f"scores={nums}, asked_clarifying={asked}"
        else:  # final
            if len(parts) != 2:
                raise ValueError
            nums = [int(x) for x in parts]
            if any(x < 0 or x > 3 for x in nums):
                raise ValueError
            final_avg = sum(nums) / 2
            rubric = f"self_intro={nums[0]}, depth={nums[1]}"
    except ValueError:
        await message.answer("Неверный формат. Пришли значения строго по шаблону из прошлого сообщения.")
        return

    await state.update_data(final_avg=round(final_avg, 2), rubric=rubric)
    await state.set_state(EvaluationFlow.waiting_comment)
    await message.answer(
        "Добавь краткий комментарий по кандидату.\n"
        "Правило честности: если сомневаешься между 1 и 2 — ставь 1."
    )


@router.message(EvaluationFlow.waiting_comment)
async def eval_comment(message: Message, state: FSMContext):
    comment = (message.text or "").strip()
    if not comment:
        await message.answer("Комментарий не может быть пустым")
        return

    data = await state.get_data()
    avg = float(data["final_avg"])
    candidate_username = data["candidate_username"]
    track_code = data.get("track_code", "unknown")

    if avg >= 2.5:
        verdict = "готов к рынку"
    elif avg >= 2.0:
        verdict = "стоит немного доработать ответы"
    else:
        verdict = "рано, продолжаем подготовку"

    candidate_tg_user_id = None

    async with SessionLocal() as session:
        item = QuickEvaluation(
            interviewer_tg_user_id=message.from_user.id,
            candidate_username=candidate_username,
            set_id=data.get("set_id"),
            score=int(round(avg * 100)),  # храним средний балл * 100
            comment=f"avg={avg}; verdict={verdict}; rubric={data.get('rubric')}; note={comment}",
        )
        session.add(item)

        candidate_user = (
            await session.execute(select(User).where(func.lower(User.username) == candidate_username.lower()))
        ).scalar_one_or_none()
        if candidate_user:
            candidate_tg_user_id = candidate_user.tg_user_id

        await session.commit()

    # 1) Отправка кандидату (если найден в базе)
    if candidate_tg_user_id:
        try:
            await message.bot.send_message(
                candidate_tg_user_id,
                "По тебе заполнена оценка собеседования 📌\n"
                f"Трек: {TRACK_LABELS.get(track_code, track_code)}\n"
                f"Средний балл: {avg}\n"
                f"Итог: {verdict}\n"
                f"Комментарий: {comment}",
            )
        except Exception:
            pass

    # 2) Отправка админу(ам)
    for admin_id in settings.admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                "Новая оценка собеседования ✅\n"
                f"Интервьюер: @{message.from_user.username or 'no_username'} (id={message.from_user.id})\n"
                f"Кандидат: @{candidate_username}\n"
                f"Трек: {TRACK_LABELS.get(track_code, track_code)}\n"
                f"Средний балл: {avg}\n"
                f"Итог: {verdict}\n"
                f"Рубрика: {data.get('rubric')}\n"
                f"Комментарий: {comment}",
            )
        except Exception:
            pass

    await state.clear()
    delivery_note = ""
    if not candidate_tg_user_id:
        delivery_note = "\nКандидат не найден в базе по username — ему не доставлено."

    await message.answer(
        "Форма оценки сохранена ✅\n"
        f"Средний балл: {avg}\n"
        f"Итог: {verdict}"
        f"{delivery_note}"
    )


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

            track_rows = (
                await session.execute(
                    select(CandidateSet.track_code, func.avg(QuickEvaluation.score), func.count(QuickEvaluation.id))
                    .join(CandidateSet, CandidateSet.id == QuickEvaluation.set_id)
                    .where(func.lower(QuickEvaluation.candidate_username) == username.lower())
                    .group_by(CandidateSet.track_code)
                )
            ).all()
            tracks_text = "\n".join(
                f"  • {track}: avg={round((avg100 or 0)/100, 2)} (n={n})" for track, avg100, n in track_rows
            ) or "  • нет данных"

            text = (
                f"Админ-статистика для @{username} (как собеседуемый):\n"
                f"— Кол-во прохождений: {cnt}\n"
                f"— Средняя оценка: {round(avg, 2) if avg is not None else 'n/a'}\n"
                f"— По трекам (из форм оценок):\n{tracks_text}"
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

            track_rows = (
                await session.execute(
                    select(CandidateSet.track_code, func.avg(QuickEvaluation.score), func.count(QuickEvaluation.id))
                    .join(CandidateSet, CandidateSet.id == QuickEvaluation.set_id)
                    .where(QuickEvaluation.interviewer_tg_user_id == db_user.tg_user_id)
                    .group_by(CandidateSet.track_code)
                )
            ).all()
            tracks_text = "\n".join(
                f"  • {track}: avg={round((avg100 or 0)/100, 2)} (n={n})" for track, avg100, n in track_rows
            ) or "  • нет данных"

            text = (
                f"Админ-статистика для @{username} (как собеседующий):\n"
                f"— Кол-во проведений: {cnt}\n"
                f"— Средняя оценка от собеседуемых: {round(avg, 2) if avg is not None else 'n/a'}\n"
                f"— По трекам (из форм оценок):\n{tracks_text}"
            )

    await state.clear()
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data.startswith("set_submission:approve:"))
async def admin_submission_approve(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    submission_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        submission = (
            await session.execute(select(CandidateSet).where(CandidateSet.id == submission_id))
        ).scalar_one_or_none()
        if not submission:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        submission.status = "approved"
        submission.admin_comment = "Принято"
        await session.commit()

        student = (
            await session.execute(select(User).where(User.id == submission.owner_user_id))
        ).scalar_one_or_none()

    if student:
        await callback.bot.send_message(
            student.tg_user_id,
            f"Твой набор '{submission.title}' ({TRACK_LABELS.get(submission.track_code, submission.track_code)}) принят ✅"
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
        submission = (
            await session.execute(select(CandidateSet).where(CandidateSet.id == submission_id))
        ).scalar_one_or_none()
        if not submission:
            await state.clear()
            await message.answer("Заявка не найдена.")
            return

        submission.status = "changes_requested"
        submission.admin_comment = comment
        await session.commit()

        student = (
            await session.execute(select(User).where(User.id == submission.owner_user_id))
        ).scalar_one_or_none()

    if student:
        await message.bot.send_message(
            student.tg_user_id,
            "По твоему набору нужны правки ✏️\n"
            f"set_id={submission_id}\n"
            f"Комментарий админа:\n{comment}\n\n"
            "Просто ответь на это сообщение одним сообщением (ссылкой или текстом исправленного набора), и я отправлю на повторную проверку админу."
        )

    await state.clear()
    await message.answer(f"Отправил правки ученику по set_id={submission_id}.")
