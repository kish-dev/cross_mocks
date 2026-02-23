import re
import random
from urllib.parse import urlencode
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from app.config import settings
from app.db.models import User, Session, SessionFeedback, CandidateSet, QuickEvaluation, PairStats, InterviewProposal, SessionReview
from app.db.session import SessionLocal
from app.repositories.users import UsersRepo
from app.bot.keyboards.common import (
    main_menu_keyboard,
    admin_role_keyboard,
    admin_submission_review_keyboard,
    track_keyboard,
    evaluation_keyboard,
    start_session_keyboard,
    start_only_keyboard,
)
from app.services.scheduling import extract_datetime_slots, can_confirm_slot
from app.services.sheets_sink import sheets_sink
from app.services.notifications import build_time_proposal_payload

router = Router()

TRACK_LABELS = {
    "theory": "theory",
    "sysdesign": "system-design",
    "livecoding": "livecoding",
    "final": "final",
}


def to_gcal_link(title: str, details: str, start_dt: datetime, end_dt: datetime) -> str:
    fmt = "%Y%m%dT%H%M%SZ"
    params = {
        "action": "TEMPLATE",
        "text": title,
        "details": details,
        "dates": f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}",
    }
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"


def interviewer_rubric_text(track_code: str) -> str:
    common = (
        "Общая шкала 0–3:\n"
        "0 — провал; 1 — слабо; 2 — нормально (middle); 3 — отлично (senior).\n"
        "Правило честности: если сомневаешься между 1 и 2 — ставь 1."
    )
    if track_code == "theory":
        specifics = (
            "Theory:\n"
            "0 — не знает/путается; 1 — знает определения без применения;\n"
            "2 — корректно с подсказками; 3 — объясняет, дает пример из практики, отвечает на уточнения.\n"
            "Важно: без примера из опыта максимум 2."
        )
    elif track_code == "livecoding":
        specifics = (
            "Livecoding:\n"
            "0 — не может начать; 1 — теряется; 2 — решает с 1–2 подсказками; 3 — решает самостоятельно и проговаривает ход мыслей.\n"
            "Минусы: молчание, попытка писать идеально, отсутствие объяснений."
        )
    elif track_code == "sysdesign":
        specifics = (
            "System-design:\n"
            "0 — хаос без структуры; 1 — куски идей; 2 — структура, но слабые аргументы; 3 — структура + компромиссы.\n"
            "Если кандидат не задает уточняющие вопросы — минус 1 к итогу."
        )
    else:
        specifics = (
            "Final:\n"
            "Оцени 2 блока 0–3: (1) как рассказал о себе, (2) глубина пояснений по опыту."
        )

    summary = (
        "Итоговая интерпретация по среднему: 2.5–3.0 готов к рынку; 2.0–2.4 доработать; <2.0 рано."
    )
    return f"{common}\n\n{specifics}\n\n{summary}"


def candidate_feedback_guide() -> str:
    return (
        "Оцени качество собеса как кандидат (0–3):\n"
        "0 — бесполезно/токсично; 1 — слабо структурировано; 2 — полезно и корректно; 3 — очень полезно, четкий фидбек и комфортное общение.\n"
        "Отдельно в комментарии: что было полезно и что улучшить по коммуникации."
    )


async def safe_send(bot, tg_user_id: int, text: str, **kwargs):
    try:
        await bot.send_message(tg_user_id, text, **kwargs)
        return True, ""
    except Exception as e:
        return False, str(e)


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


class SchedulingFlow(StatesGroup):
    waiting_time_options = State()


class SessionClosureFlow(StatesGroup):
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


@router.message(F.reply_to_message)
async def meeting_link_via_reply(message: Message, state: FSMContext):
    reply_text = ((message.reply_to_message.text or "") + "\n" + (message.reply_to_message.caption or "")).strip()
    m = re.search(r"session_id=(\d+)", reply_text)
    if not m:
        return

    session_id = int(m.group(1))
    content = (message.text or message.caption or "").strip()
    url_match = re.search(r"https?://\S+", content)

    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        s = (await session.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
        if not me or not s:
            await message.answer("Сессия не найдена.")
            return

        # 1) Interviewer sends meeting link
        if url_match and me.id == s.interviewer_id:
            meeting_url = url_match.group(0)
            candidate = (await session.execute(select(User).where(User.id == s.student_id))).scalar_one_or_none()
            s.meeting_url = meeting_url
            await session.commit()

            await message.answer("Ссылку отправил кандидату ✅")
            if candidate:
                try:
                    await message.bot.send_message(
                        candidate.tg_user_id,
                        "Ссылка на созвон от интервьюера:\n"
                        f"{meeting_url}\n"
                        f"session_id={session_id}",
                    )
                    await message.bot.send_message(
                        candidate.tg_user_id,
                        "Как оценить качество собеса и общение:\n"
                        f"{candidate_feedback_guide()}"
                    )
                except Exception:
                    pass

            try:
                await message.bot.send_message(
                    me.tg_user_id,
                    "Гайд оценки для собеседующего:\n"
                    f"{interviewer_rubric_text(s.track_code)}"
                )
            except Exception:
                pass
            return

        # 2) Participant sends feedback by reply with session_id (fallback, no FSM required)
        if me.id in {s.student_id, s.interviewer_id} and content:
            target_id = s.interviewer_id if me.id == s.student_id else s.student_id
            role = "candidate" if me.id == s.student_id else "interviewer"
            m_score = re.search(r"итог\s*:\s*(\d+)", content.lower())
            score = int(m_score.group(1)) if m_score else 0

            existing = (
                await session.execute(
                    select(SessionReview).where(SessionReview.session_id == session_id, SessionReview.author_user_id == me.id)
                )
            ).scalar_one_or_none()
            if existing:
                existing.score = score
                existing.comment = content
            else:
                session.add(
                    SessionReview(
                        session_id=session_id,
                        author_user_id=me.id,
                        target_user_id=target_id,
                        author_role=role,
                        score=score,
                        comment=content,
                    )
                )
            await session.commit()
            await message.answer("Фидбек сохранен ✅")
            return

    # if it is reply to session but not valid action
    if url_match and me and s and me.id != s.interviewer_id:
        await message.answer("Ссылку на созвон может отправить только собеседующий.")


@router.message()
async def meeting_link_without_reply(message: Message, state: FSMContext):
    # interviewer can send telemost link without reply; bot routes to candidate of nearest active session
    current_state = await state.get_state()
    if current_state is not None:
        return

    content = (message.text or message.caption or "").strip()
    if not content:
        return

    url_match = re.search(r"https?://\S+", content)
    if not url_match:
        return

    meeting_url = url_match.group(0)

    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not me:
            return

        # nearest upcoming/active session where sender is interviewer
        s = (
            await session.execute(
                select(Session)
                .where(
                    Session.interviewer_id == me.id,
                    Session.status.in_(["scheduled", "in_progress"]),
                )
                .order_by(Session.starts_at.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not s:
            return

        candidate = (await session.execute(select(User).where(User.id == s.student_id))).scalar_one_or_none()
        if not candidate:
            return

        s.meeting_url = meeting_url
        await session.commit()

    ok1, err1 = await safe_send(
        message.bot,
        candidate.tg_user_id,
        "Ссылка на созвон от интервьюера:\n"
        f"{meeting_url}\n"
        f"session_id={s.id}",
    )
    ok2, err2 = await safe_send(
        message.bot,
        candidate.tg_user_id,
        "Как оценить качество собеса и общение:\n"
        f"{candidate_feedback_guide()}"
    )

    if ok1 and ok2:
        await message.answer(f"Ссылку отправил кандидату для session_id={s.id} ✅")
    else:
        await message.answer(
            f"Не удалось полностью доставить кандидату для session_id={s.id}.\n"
            f"link={ok1} ({err1})\nguide={ok2} ({err2})"
        )

    await safe_send(
        message.bot,
        me.tg_user_id,
        "Гайд оценки для собеседующего:\n"
        f"{interviewer_rubric_text(s.track_code)}"
    )


@router.message(F.reply_to_message)
async def resubmit_via_reply(message: Message, state: FSMContext):
    # one-click flow: user replies to admin changes message with updated set content
    reply_text = ((message.reply_to_message.text or "") + "\n" + (message.reply_to_message.caption or "")).strip()
    m = re.search(r"set_id=(\d+)", reply_text)

    # cancel any stale FSM state so reply-based resubmission always works
    await state.clear()

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

        # fallback: if set_id not parsed (or old message), use latest changes_requested set for this user
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
                "Ответь именно на сообщение бота с правками или попроси админа заново отправить правки."
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


@router.callback_query(F.data == "menu:find_interviewer")
async def find_interviewer(callback: CallbackQuery):
    await callback.message.answer("Выбери тему собеса, который хочешь пройти:", reply_markup=track_keyboard("pass_track"))
    await callback.answer()


@router.callback_query(F.data.startswith("pass_track:"))
async def pass_track(callback: CallbackQuery, state: FSMContext):
    track = callback.data.split(":", 1)[1]

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.message.answer("Сначала нажми /start")
            await callback.answer()
            return

        approved_for_track = (
            await session.execute(
                select(func.count(CandidateSet.id)).where(
                    CandidateSet.owner_user_id == db_user.id,
                    CandidateSet.status == "approved",
                    CandidateSet.track_code == track,
                )
            )
        ).scalar_one()

    if approved_for_track < 1:
        await callback.message.answer(
            "Чтобы пройти собес по этой теме, у тебя должен быть минимум 1 одобренный набор по ней.\n"
            "Сначала отправь набор на проверку админу."
        )
        await callback.answer()
        return

    async with SessionLocal() as session:
        # кандидаты-интервьюеры: есть approved набор по треку, не сам пользователь
        candidates = (
            await session.execute(
                select(User)
                .join(CandidateSet, CandidateSet.owner_user_id == User.id)
                .where(
                    User.id != db_user.id,
                    User.is_active.is_(True),
                    CandidateSet.status == "approved",
                    CandidateSet.track_code == track,
                )
                .group_by(User.id)
            )
        ).scalars().all()

        if not candidates:
            await callback.message.answer("Пока нет доступных интервьюеров по этой теме. Попробуй позже.")
            await callback.answer()
            return

        never_had = []
        had_other_topic = []
        had_same_topic = []

        for candidate in candidates:
            pair_sessions = (
                await session.execute(
                    select(Session.track_code, Session.starts_at).where(
                        ((Session.student_id == db_user.id) & (Session.interviewer_id == candidate.id))
                        | ((Session.student_id == candidate.id) & (Session.interviewer_id == db_user.id))
                    )
                )
            ).all()

            if not pair_sessions:
                never_had.append(candidate)
                continue

            had_same_track = any(t == track for t, _ in pair_sessions)
            if had_same_track:
                had_same_topic.append(candidate)
            else:
                had_other_topic.append(candidate)

        # топ-5 в каждой категории
        top_never = never_had[:5]
        top_other = had_other_topic[:5]
        top_same = had_same_topic[:5]

        if not top_never and not top_other and not top_same:
            await callback.message.answer("По этой теме нет доступных кандидатов. Попробуй позже.")
            await callback.answer()
            return

    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    if top_never:
        for u in top_never:
            kb.button(text=f"🆕 @{u.username or u.id} (без собеса)", callback_data=f"pass_pick:{track}:{u.id}")
    if top_other:
        for u in top_other:
            kb.button(text=f"🔁 @{u.username or u.id} (другая тема)", callback_data=f"pass_pick:{track}:{u.id}")
    if top_same:
        for u in top_same:
            kb.button(text=f"⚠️ @{u.username or u.id} (уже был собес по этой теме)", callback_data=f"pass_pick:{track}:{u.id}")

    pool_ids = [u.id for u in top_never + top_other + top_same]
    await state.update_data(track=track, candidate_pool=pool_ids)
    kb.button(text="🎲 Выбрать случайного", callback_data=f"pass_random:{track}")
    kb.adjust(1)

    await callback.message.answer(
        "Выбери кандидата для собеса:\n"
        "— сначала топ-5, с кем ещё не было собеса\n"
        "— затем топ-5, с кем был собес на другой теме\n"
        "— ⚠️ также показываем тех, с кем уже был собес по этой теме (проводить можно)",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pass_pick:"))
async def pass_pick_candidate(callback: CallbackQuery, state: FSMContext):
    _, track, interviewer_id = callback.data.split(":", 2)

    async with SessionLocal() as session:
        interviewer = (await session.execute(select(User).where(User.id == int(interviewer_id)))).scalar_one_or_none()
    if not interviewer:
        await callback.message.answer("Кандидат не найден.")
        await callback.answer()
        return

    await state.set_state(SchedulingFlow.waiting_time_options)
    await state.update_data(track=track, interviewer_id=int(interviewer_id))

    await callback.message.answer(
        f"Выбран интервьюер: @{interviewer.username or 'no_username'} ✅\n"
        "Пришли удобное время в формате YYYY-MM-DD HH:MM MSK, например: 2026-02-24 19:30"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pass_random:"))
async def pass_random_candidate(callback: CallbackQuery, state: FSMContext):
    track = callback.data.split(":", 1)[1]
    data = await state.get_data()
    pool = data.get("candidate_pool") or []
    if not pool:
        await callback.message.answer("Пул кандидатов пуст, выбери тему заново.")
        await callback.answer()
        return

    interviewer_id = random.choice(pool)

    async with SessionLocal() as session:
        interviewer = (await session.execute(select(User).where(User.id == int(interviewer_id)))).scalar_one_or_none()
    if not interviewer:
        await callback.message.answer("Случайный кандидат недоступен, попробуй ещё раз.")
        await callback.answer()
        return

    await state.set_state(SchedulingFlow.waiting_time_options)
    await state.update_data(track=track, interviewer_id=int(interviewer_id))

    await callback.message.answer(
        f"Случайный выбор: @{interviewer.username or 'no_username'} 🎲\n"
        "Пришли удобное время в формате YYYY-MM-DD HH:MM MSK, например: 2026-02-24 19:30"
    )
    await callback.answer()


@router.message(SchedulingFlow.waiting_time_options)
async def schedule_after_match(message: Message, state: FSMContext):
    request_text = (message.text or "").strip()
    if not request_text:
        await message.answer("Опиши удобные временные рамки в свободной форме, например: 'завтра после 18:00' или 'весь день в среду'.")
        return

    data = await state.get_data()
    track = data.get("track")
    interviewer_id = data.get("interviewer_id")
    if not track or not interviewer_id:
        await state.clear()
        await message.answer("Сессия подбора потерялась. Нажми «Хочу пройти собес» ещё раз.")
        return

    async with SessionLocal() as session:
        student = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        interviewer = (await session.execute(select(User).where(User.id == interviewer_id))).scalar_one_or_none()
        if not student or not interviewer:
            await state.clear()
            await message.answer("Не удалось создать запрос на собес, попробуй ещё раз.")
            return

        set_item = (
            await session.execute(
                select(CandidateSet)
                .where(CandidateSet.owner_user_id == interviewer.id, CandidateSet.track_code == track, CandidateSet.status == "approved")
                .order_by(CandidateSet.updated_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not set_item:
            await state.clear()
            await message.answer("У интервьюера не найден подходящий набор. Запусти подбор ещё раз.")
            return

        # try to extract exact datetime slots from free-form text: YYYY-MM-DD HH:MM
        parsed_slots = extract_datetime_slots(request_text)

        proposal = InterviewProposal(
            student_id=student.id,
            interviewer_id=interviewer.id,
            track_code=track,
            pack_id=set_item.id,
            options_json={"request": request_text, "parsed_slots": parsed_slots[:5]},
            status="pending",
        )
        session.add(proposal)
        await session.commit()
        await session.refresh(proposal)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for idx, slot in enumerate((proposal.options_json or {}).get("parsed_slots", [])):
        kb.button(text=f"✅ {slot}", callback_data=f"proposal:offer:{proposal.id}:{idx}")
    kb.button(text="🕒 Предложить итоговый слот", callback_data=f"proposal:propose:{proposal.id}")
    kb.adjust(1)

    await state.clear()

    payload = build_time_proposal_payload(
        interviewer_tg_user_id=interviewer.tg_user_id,
        student_tg_user_id=message.from_user.id,
        request_text=request_text,
        track_label=TRACK_LABELS.get(track, track),
        candidate_username=(message.from_user.username or 'no_username'),
    )

    await message.answer(payload.student_text)

    ok, err = await safe_send(
        message.bot,
        payload.interviewer_tg_user_id,
        payload.interviewer_text,
        reply_markup=kb.as_markup(),
    )
    if not ok:
        await message.answer(
            "Не удалось отправить запрос интервьюеру. Проверь, что он запускал /start и доступен боту.\n"
            f"Техдеталь: {err}"
        )


class ProposalFlow(StatesGroup):
    waiting_final_time = State()


@router.callback_query(F.data.startswith("proposal:offer:"))
async def proposal_offer_preparsed(callback: CallbackQuery):
    _, _, proposal_id, idx = callback.data.split(":", 3)
    async with SessionLocal() as session:
        proposal = (await session.execute(select(InterviewProposal).where(InterviewProposal.id == int(proposal_id)))).scalar_one_or_none()
        interviewer = (await session.execute(select(User).where(User.id == proposal.interviewer_id))).scalar_one_or_none() if proposal else None
        student = (await session.execute(select(User).where(User.id == proposal.student_id))).scalar_one_or_none() if proposal else None

        if not proposal or not interviewer or not student:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        if callback.from_user.id != interviewer.tg_user_id:
            await callback.answer("Это не твоя заявка", show_alert=True)
            return

        slots = (proposal.options_json or {}).get("parsed_slots", [])
        i = int(idx)
        if i < 0 or i >= len(slots):
            await callback.answer("Слот не найден", show_alert=True)
            return

        picked = slots[i]
        proposal.options_json = {**(proposal.options_json or {}), "final_time": picked}
        await session.commit()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Слот кайф, подтверждаю", callback_data=f"proposal:confirm:{proposal_id}")
    kb.button(text="❌ Не подходит", callback_data=f"proposal:reject:{proposal_id}")
    kb.adjust(1)

    await callback.message.answer("Слот отправлен кандидату на подтверждение ✅")
    await callback.answer()

    try:
        await callback.bot.send_message(
            student.tg_user_id,
            "Интервьюер предложил итоговое время:\n"
            f"{picked} MSK\n"
            "Подтверди слот:",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("proposal:propose:"))
async def proposal_start_propose(callback: CallbackQuery, state: FSMContext):
    proposal_id = int(callback.data.split(":")[-1])
    async with SessionLocal() as session:
        proposal = (await session.execute(select(InterviewProposal).where(InterviewProposal.id == proposal_id))).scalar_one_or_none()
        interviewer = (await session.execute(select(User).where(User.id == proposal.interviewer_id))).scalar_one_or_none() if proposal else None

    if not proposal or not interviewer:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    if callback.from_user.id != interviewer.tg_user_id:
        await callback.answer("Это не твоя заявка", show_alert=True)
        return

    await state.set_state(ProposalFlow.waiting_final_time)
    await state.update_data(proposal_id=proposal_id)
    await callback.message.answer("Введи итоговое время в формате YYYY-MM-DD HH:MM MSK")
    await callback.answer()


@router.message(ProposalFlow.waiting_final_time)
async def proposal_receive_final_time(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M")
    except ValueError:
        await message.answer("Неверный формат. Используй YYYY-MM-DD HH:MM")
        return

    data = await state.get_data()
    proposal_id = data.get("proposal_id")
    if not proposal_id:
        await state.clear()
        await message.answer("Сессия потерялась. Нажми кнопку ещё раз.")
        return

    async with SessionLocal() as session:
        proposal = (await session.execute(select(InterviewProposal).where(InterviewProposal.id == int(proposal_id)))).scalar_one_or_none()
        if not proposal or proposal.status != "pending":
            await state.clear()
            await message.answer("Заявка уже обработана")
            return

        interviewer = (await session.execute(select(User).where(User.id == proposal.interviewer_id))).scalar_one_or_none()
        student = (await session.execute(select(User).where(User.id == proposal.student_id))).scalar_one_or_none()
        if not interviewer or not student:
            await state.clear()
            await message.answer("Не удалось найти участников")
            return

        proposal.options_json = {**(proposal.options_json or {}), "final_time": raw}
        await session.commit()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Слот кайф, подтверждаю", callback_data=f"proposal:confirm:{proposal_id}")
    kb.button(text="❌ Не подходит", callback_data=f"proposal:reject:{proposal_id}")
    kb.adjust(1)

    await state.clear()
    await message.answer("Отправил слот кандидату на подтверждение ✅")

    ok, err = await safe_send(
        message.bot,
        student.tg_user_id,
        "Интервьюер предложил итоговое время:\n"
        f"{raw} MSK\n"
        "Подтверди слот:",
        reply_markup=kb.as_markup(),
    )
    if not ok:
        await message.answer(
            "Не удалось отправить слот кандидату. Проверь, что кандидат запускал /start и доступен боту.\n"
            f"Техдеталь: {err}"
        )


@router.callback_query(F.data.startswith("proposal:reject:"))
async def proposal_reject(callback: CallbackQuery):
    proposal_id = int(callback.data.split(":")[-1])
    async with SessionLocal() as session:
        proposal = (await session.execute(select(InterviewProposal).where(InterviewProposal.id == proposal_id))).scalar_one_or_none()
        if not proposal:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        student = (await session.execute(select(User).where(User.id == proposal.student_id))).scalar_one_or_none()
        interviewer = (await session.execute(select(User).where(User.id == proposal.interviewer_id))).scalar_one_or_none()

    if not student or callback.from_user.id != student.tg_user_id:
        await callback.answer("Только кандидат может отклонить", show_alert=True)
        return

    await callback.answer("Отклонено")
    await callback.message.answer("Ок, слот отклонён. Интервьюер предложит другой.")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🕒 Предложить другое время", callback_data=f"proposal:propose:{proposal_id}")
    kb.adjust(1)

    try:
        await callback.bot.send_message(
            interviewer.tg_user_id,
            "Кандидат отклонил слот. Предложи другое время:",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("proposal:confirm:"))
async def proposal_confirm(callback: CallbackQuery):
    proposal_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        proposal = (await session.execute(select(InterviewProposal).where(InterviewProposal.id == int(proposal_id)))).scalar_one_or_none()
        picked_str = ((proposal.options_json or {}).get("final_time") if proposal else None)
        if not proposal:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        if not can_confirm_slot(proposal.status, picked_str):
            await callback.answer("Слот не выбран или заявка уже обработана", show_alert=True)
            return
        try:
            starts_at = datetime.strptime(picked_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await callback.answer("Некорректное время", show_alert=True)
            return

        interviewer = (await session.execute(select(User).where(User.id == proposal.interviewer_id))).scalar_one_or_none()
        student = (await session.execute(select(User).where(User.id == proposal.student_id))).scalar_one_or_none()
        if not interviewer or not student:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        if callback.from_user.id != student.tg_user_id:
            await callback.answer("Это подтверждает кандидат", show_alert=True)
            return

        ends_at = starts_at + timedelta(minutes=settings.DEFAULT_DURATION_MIN)

        session_row = Session(
            interviewer_id=interviewer.id,
            student_id=student.id,
            track_code=proposal.track_code,
            pack_id=proposal.pack_id,
            starts_at=starts_at,
            ends_at=ends_at,
            meeting_url=settings.TELEMOST_URL,
            status="scheduled",
        )
        session.add(session_row)
        proposal.status = "accepted"

        a, b = sorted((student.id, interviewer.id))
        pair = (await session.execute(select(PairStats).where(PairStats.user_a_id == a, PairStats.user_b_id == b))).scalar_one_or_none()
        if not pair:
            pair = PairStats(user_a_id=a, user_b_id=b, interviews_count=0)
            session.add(pair)
        pair.interviews_count += 1
        pair.last_interview_at = datetime.utcnow()

        await session.commit()
        await session.refresh(session_row)

    sheets_sink.send(
        "session_scheduled",
        {
            "session_id": session_row.id,
            "track": session_row.track_code,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "student_tg_user_id": student.tg_user_id,
            "interviewer_tg_user_id": interviewer.tg_user_id,
            "meeting_url": session_row.meeting_url,
            "timezone": "MSK",
        },
    )

    await callback.message.answer(f"Слот подтвержден: {picked_str} ✅")
    await callback.answer()

    details = f"Собес по теме {TRACK_LABELS.get(session_row.track_code, session_row.track_code)}. Telemost: {session_row.meeting_url}"
    gcal = to_gcal_link(
        title=f"Mock interview: {TRACK_LABELS.get(session_row.track_code, session_row.track_code)}",
        details=details,
        start_dt=starts_at,
        end_dt=ends_at,
    )

    try:
        await callback.bot.send_message(
            student.tg_user_id,
            "Собес назначен ✅\n"
            f"Тема: {TRACK_LABELS.get(session_row.track_code, session_row.track_code)}\n"
            f"Когда: {picked_str} MSK\n"
            f"Добавить в календарь: {gcal}\n"
            "Интервьюер пришлет ссылку на созвон отдельным сообщением.",
            reply_markup=start_only_keyboard(session_row.id),
        )
    except Exception:
        pass

    try:
        # interviewer also receives questions for this interview
        async with SessionLocal() as session2:
            set_item2 = (await session2.execute(select(CandidateSet).where(CandidateSet.id == session_row.pack_id))).scalar_one_or_none()

        candidate_nick = f"@{student.username}" if student.username else f"id:{student.tg_user_id}"

        await callback.bot.send_message(
            interviewer.tg_user_id,
            "Собес назначен ✅\n"
            f"Тема: {TRACK_LABELS.get(session_row.track_code, session_row.track_code)}\n"
            f"Когда: {picked_str} MSK\n"
            f"Кандидат: {candidate_nick}\n"
            f"session_id={session_row.id}\n"
            f"Добавить в календарь: {gcal}\n\n"
            "Сначала создай встречу в Telemost и ОТВЕТЬ на это сообщение ссылкой — бот перешлёт её кандидату.\n\n"
            "Вопросы для собеса:\n"
            f"{set_item2.questions_text if set_item2 else 'n/a'}\n\n"
            "Можно запустить собес кнопкой ниже.",
            reply_markup=start_only_keyboard(session_row.id),
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("session:start_now:"))
async def session_start_now(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        s = (await session.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
        if not s:
            await callback.answer("Собес не найден", show_alert=True)
            return

        me = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not me or me.id not in {s.student_id, s.interviewer_id}:
            await callback.answer("Это не твой собес", show_alert=True)
            return

        # immediate start without auto-generating private meeting link
        s.starts_at = datetime.utcnow()
        s.ends_at = s.starts_at + timedelta(minutes=settings.DEFAULT_DURATION_MIN)
        s.status = "in_progress"
        await session.commit()

        student = (await session.execute(select(User).where(User.id == s.student_id))).scalar_one_or_none()
        interviewer = (await session.execute(select(User).where(User.id == s.interviewer_id))).scalar_one_or_none()

    for u in [student, interviewer]:
        if not u:
            continue
        try:
            await callback.bot.send_message(
                u.tg_user_id,
                "⚡ Собес начинается сейчас!\n"
                f"Базовая ссылка Telemost: {settings.TELEMOST_URL}\n"
                "Если нужна приватная встреча — интервьюер создает её и отправляет ссылку кандидату reply-сообщением.",
            )
        except Exception:
            pass

    await callback.answer("Старт сейчас отправлен обоим", show_alert=True)


@router.callback_query(F.data.startswith("session:start:"))
async def session_start(callback: CallbackQuery, state: FSMContext):
    session_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        s = (await session.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
        if not s:
            await callback.answer("Собес не найден", show_alert=True)
            return
        me = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not me or me.id not in {s.student_id, s.interviewer_id}:
            await callback.answer("Это не твой собес", show_alert=True)
            return

        student = (await session.execute(select(User).where(User.id == s.student_id))).scalar_one_or_none()
        interviewer = (await session.execute(select(User).where(User.id == s.interviewer_id))).scalar_one_or_none()

        first_start = False
        if s.status == "scheduled":
            s.status = "in_progress"
            await session.commit()
            first_start = True

    role = "candidate" if me.id == s.student_id else "interviewer"
    await state.set_state(SessionClosureFlow.waiting_comment)
    await state.update_data(session_id=session_id, role=role)

    # kickoff routing: notify second participant + role-specific startup prompts
    if first_start and student and interviewer:
        second_tg_id = interviewer.tg_user_id if me.id == student.id else student.tg_user_id
        ok1, err1 = await safe_send(callback.bot, second_tg_id, "Партнер нажал «Пройти собес». Собес ожидает начала.")

        ok2, err2 = await safe_send(
            callback.bot,
            interviewer.tg_user_id,
            "Создай ссылку на созвон в Telemost:\n"
            f"{settings.TELEMOST_URL}\n\n"
            f"Кандидат: @{student.username if student.username else student.tg_user_id}\n"
            f"session_id={session_id}\n"
            "Отправь ссылку reply-ответом или обычным сообщением — она будет направлена кандидату.",
        )

        ok3, err3 = await safe_send(
            callback.bot,
            student.tg_user_id,
            "Ссылка на созвон появится, когда интервьюер создаст её. Отправлю новым сообщением."
        )

        if not (ok1 and ok2 and ok3):
            await callback.message.answer(
                "⚠️ Не все служебные сообщения доставлены.\n"
                f"second={ok1} ({err1})\ninterviewer={ok2} ({err2})\nstudent={ok3} ({err3})"
            )

    # no extra prompt for candidate here; feedback request happens later in flow
    await callback.answer()


# SessionClosureFlow uses free-form single-step feedback in waiting_comment

@router.message(SessionClosureFlow.waiting_comment)
async def session_review_comment(message: Message, state: FSMContext):
    comment = (message.text or "").strip()
    if not comment:
        await message.answer("Комментарий не может быть пустым")
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    role = data.get("role")

    m = re.search(r"итог\s*:\s*(\d+)", comment.lower())
    score = int(m.group(1)) if m else 0

    async with SessionLocal() as session:
        s = (await session.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
        me = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not s or not me:
            await state.clear()
            await message.answer("Собес не найден")
            return

        target_id = s.interviewer_id if me.id == s.student_id else s.student_id

        existing = (
            await session.execute(
                select(SessionReview).where(SessionReview.session_id == session_id, SessionReview.author_user_id == me.id)
            )
        ).scalar_one_or_none()
        if existing:
            existing.score = score
            existing.comment = comment
        else:
            session.add(
                SessionReview(
                    session_id=session_id,
                    author_user_id=me.id,
                    target_user_id=target_id,
                    author_role=role,
                    score=score,
                    comment=comment,
                )
            )

        reviews = (
            await session.execute(select(SessionReview).where(SessionReview.session_id == session_id))
        ).scalars().all()

        await session.commit()

        await state.clear()
        await message.answer("Фидбек сохранен ✅")

        if len(reviews) >= 2:
            s.status = "completed"
            await session.commit()

            users = {
                u.id: u
                for u in (
                    await session.execute(select(User).where(User.id.in_([s.student_id, s.interviewer_id])))
                ).scalars().all()
            }

            cand_review = next((r for r in reviews if r.author_user_id == s.student_id), None)
            int_review = next((r for r in reviews if r.author_user_id == s.interviewer_id), None)

            if cand_review and int_review:
                try:
                    await message.bot.send_message(users[s.interviewer_id].tg_user_id, f"Фидбек кандидата:\nОценка: {cand_review.score}\n{cand_review.comment}")
                    await message.bot.send_message(users[s.student_id].tg_user_id, f"Фидбек интервьюера:\nОценка: {int_review.score}\n{int_review.comment}")
                except Exception:
                    pass

            sheets_sink.send(
                "session_completed",
                {
                    "session_id": session_id,
                    "track": s.track_code,
                    "candidate_feedback": {
                        "score": cand_review.score if cand_review else None,
                        "comment": cand_review.comment if cand_review else None,
                    },
                    "interviewer_feedback": {
                        "score": int_review.score if int_review else None,
                        "comment": int_review.comment if int_review else None,
                    },
                    "timezone": "MSK",
                },
            )

            for admin_id in settings.admin_ids:
                try:
                    await message.bot.send_message(
                        admin_id,
                        "Собес закрыт ✅\n"
                        f"session_id={session_id}\n"
                        f"Тема: {TRACK_LABELS.get(s.track_code, s.track_code)}\n"
                        f"Кандидат фидбек: {cand_review.score if cand_review else 'n/a'} / {cand_review.comment if cand_review else 'n/a'}\n"
                        f"Интервьюер фидбек: {int_review.score if int_review else 'n/a'} / {int_review.comment if int_review else 'n/a'}",
                    )
                except Exception:
                    pass


@router.callback_query(F.data == "menu:find_student")
async def find_student(callback: CallbackQuery):
    await callback.message.answer("Выбери трек собеса:", reply_markup=track_keyboard("conduct_track"))
    await callback.answer()


@router.callback_query(F.data.startswith("conduct_track:"))
async def conduct_track(callback: CallbackQuery):
    track = callback.data.split(":", 1)[1]

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.message.answer("Сначала нажми /start")
            await callback.answer()
            return

        rows = (
            await session.execute(
                select(CandidateSet.id, CandidateSet.title)
                .where(
                    CandidateSet.track_code == track,
                    CandidateSet.status == "approved",
                    CandidateSet.owner_user_id == db_user.id,
                )
                .order_by(CandidateSet.created_at.desc())
                .limit(20)
            )
        ).all()

    if not rows:
        await callback.message.answer("У тебя пока нет одобренных наборов по этому треку.")
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


async def _render_upcoming_page(target_message, tg_user_id: int, page: int = 0):
    now = datetime.utcnow()
    page_size = 5

    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == tg_user_id))).scalar_one_or_none()
        if not me:
            await target_message.answer("Сначала нажми /start")
            return

        rows = (
            await session.execute(
                select(Session, CandidateSet.title, User.username, User.tg_user_id)
                .join(CandidateSet, CandidateSet.id == Session.pack_id, isouter=True)
                .join(User, User.id == Session.student_id, isouter=True)
                .where(
                    Session.status == "scheduled",
                    Session.starts_at >= now,
                    ((Session.student_id == me.id) | (Session.interviewer_id == me.id)),
                )
                .order_by(Session.starts_at.asc())
            )
        ).all()

        if not rows:
            await target_message.answer("Предстоящих собесов пока нет.")
            return

        start = page * page_size
        end = start + page_size
        chunk = rows[start:end]

        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()

        lines = [f"Предстоящие собесы (страница {page + 1}) — время в MSK:"]
        for s, set_title, student_username, student_tg_id in chunk:
            is_interviewer = s.interviewer_id == me.id
            role = "собеседующий" if is_interviewer else "собеседуемый"

            # identify peer nickname
            if is_interviewer:
                peer_name = f"@{student_username}" if student_username else f"id:{student_tg_id}"
            else:
                interviewer = (
                    await session.execute(select(User).where(User.id == s.interviewer_id))
                ).scalar_one_or_none()
                peer_name = f"@{interviewer.username}" if interviewer and interviewer.username else f"id:{interviewer.tg_user_id if interviewer else 'n/a'}"

            title_part = f" | набор: {set_title or 'n/a'}" if is_interviewer else ""
            lines.append(
                f"• #{s.id} | {s.starts_at.strftime('%Y-%m-%d %H:%M')} MSK | {TRACK_LABELS.get(s.track_code, s.track_code)} | {role} | второй: {peer_name}{title_part}"
            )

            # per-session actions
            gcal = to_gcal_link(
                title=f"Mock interview: {TRACK_LABELS.get(s.track_code, s.track_code)}",
                details=f"Session #{s.id}. Telemost: {s.meeting_url}",
                start_dt=s.starts_at,
                end_dt=s.ends_at,
            )
            kb.button(text=f"📅 Календарь #{s.id}", callback_data=f"upg:cal:{s.id}")
            kb.button(text=f"🗑 Удалить #{s.id}", callback_data=f"upg:del:{s.id}")

        if page > 0:
            kb.button(text="⬅️ Назад", callback_data=f"upg:page:{page-1}")
        if end < len(rows):
            kb.button(text="Вперёд ➡️", callback_data=f"upg:page:{page+1}")
        kb.adjust(1)

    await target_message.answer("\n".join(lines), reply_markup=kb.as_markup())


@router.callback_query(F.data == "menu:upcoming")
async def upcoming_sessions(callback: CallbackQuery):
    await _render_upcoming_page(callback.message, callback.from_user.id, page=0)
    await callback.answer()


@router.callback_query(F.data.startswith("upg:page:"))
async def upcoming_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[-1])
    await _render_upcoming_page(callback.message, callback.from_user.id, page=page)
    await callback.answer()


@router.callback_query(F.data.startswith("upg:del:"))
async def upcoming_delete(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[-1])
    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        s = (await session.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
        if not me or not s or me.id not in {s.student_id, s.interviewer_id}:
            await callback.answer("Нет доступа", show_alert=True)
            return
        if s.status != "scheduled":
            await callback.answer("Можно удалить только запланированный собес", show_alert=True)
            return
        s.status = "cancelled"
        await session.commit()

    await callback.message.answer(f"Собес #{session_id} удален из расписания ✅")
    await callback.answer()


@router.callback_query(F.data.startswith("upg:cal:"))
async def upcoming_calendar(callback: CallbackQuery):
    session_id = int(callback.data.split(":")[-1])
    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        s = (await session.execute(select(Session).where(Session.id == session_id))).scalar_one_or_none()
        if not me or not s or me.id not in {s.student_id, s.interviewer_id}:
            await callback.answer("Нет доступа", show_alert=True)
            return

    gcal = to_gcal_link(
        title=f"Mock interview: {TRACK_LABELS.get(s.track_code, s.track_code)}",
        details=f"Session #{s.id}. Telemost: {s.meeting_url}",
        start_dt=s.starts_at,
        end_dt=s.ends_at,
    )
    ics_stub = f"https://calendar.google.com/calendar/ical/{s.id}.ics"
    await callback.message.answer(f"Для собеса #{s.id}:\nGoogle Calendar: {gcal}\niCal: {ics_stub}")
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

        last5_as_interviewer = (
            await session.execute(
                select(QuickEvaluation.candidate_username, QuickEvaluation.score, CandidateSet.track_code)
                .join(CandidateSet, CandidateSet.id == QuickEvaluation.set_id, isouter=True)
                .where(QuickEvaluation.interviewer_tg_user_id == db_user.tg_user_id)
                .order_by(QuickEvaluation.created_at.desc())
                .limit(5)
            )
        ).all()

        last5_as_candidate = []
        if db_user.username:
            last5_as_candidate = (
                await session.execute(
                    select(QuickEvaluation.interviewer_tg_user_id, QuickEvaluation.score, CandidateSet.track_code)
                    .join(CandidateSet, CandidateSet.id == QuickEvaluation.set_id, isouter=True)
                    .where(func.lower(QuickEvaluation.candidate_username) == db_user.username.lower())
                    .order_by(QuickEvaluation.created_at.desc())
                    .limit(5)
                )
            ).all()

    interviewer_lines = "\n".join(
        f"  • @{cand}: {round(score/100, 2)} ({TRACK_LABELS.get(track or 'unknown', track or 'unknown')})"
        for cand, score, track in last5_as_interviewer
    ) or "  • нет данных"

    candidate_lines = "\n".join(
        f"  • interviewer_id={int_id}: {round(score/100, 2)} ({TRACK_LABELS.get(track or 'unknown', track or 'unknown')})"
        for int_id, score, track in last5_as_candidate
    ) or "  • нет данных"

    await callback.message.answer(
        "Твоя статистика:\n"
        f"— Проходил собесы: {passed_count}\n"
        f"— Проводил собесы: {conducted_count}\n"
        f"— Средняя оценка как собеседуемый: {round(avg_as_student, 2) if avg_as_student is not None else 'n/a'}\n"
        f"— Средняя оценка как собеседующий: {round(avg_as_interviewer, 2) if avg_as_interviewer is not None else 'n/a'}\n\n"
        f"Последние 5 как интервьюер:\n{interviewer_lines}\n\n"
        f"Последние 5 как собеседуемый:\n{candidate_lines}"
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


@router.message()
async def auto_resubmit_latest_changes(message: Message, state: FSMContext):
    # if user has pending changes_requested set, any plain message auto-resubmits it to admin
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


