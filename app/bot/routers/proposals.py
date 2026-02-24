import random
import re
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.keyboards.common import start_only_keyboard
from app.bot.routers.shared import TRACK_LABELS, continue_menu_for_user, safe_send, to_gcal_link
from app.config import settings
from app.db.models import CandidateSet, InterviewProposal, PairStats, Session, User
from app.db.session import SessionLocal
from app.services.notifications import build_time_proposal_payload
from app.services.review_guards import (
    build_pending_review_block_text,
    get_pending_interviewer_reviews_for_tg_user,
)
from app.services.scheduling import can_confirm_slot, extract_datetime_slots, is_future_slot, normalize_datetime_input
from app.services.sheets_sink import sheets_sink
from app.utils.time import utcnow

router = Router()


class SchedulingFlow(StatesGroup):
    waiting_time_options = State()


class ProposalFlow(StatesGroup):
    waiting_final_time = State()


def _looks_like_feedback_text(text: str) -> bool:
    normalized = text.strip().lower()
    return bool(re.search(r"(итог|оцен|балл|фидбек|\d+[,.]\d+)", normalized))


@router.callback_query(F.data.startswith("pass_track:"))
async def pass_track(callback: CallbackQuery, state: FSMContext):
    async with SessionLocal() as session:
        pending = await get_pending_interviewer_reviews_for_tg_user(
            session,
            tg_user_id=callback.from_user.id,
        )
    if pending:
        await callback.message.answer(build_pending_review_block_text(pending))
        await callback.answer()
        return

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
    async with SessionLocal() as session:
        pending = await get_pending_interviewer_reviews_for_tg_user(
            session,
            tg_user_id=callback.from_user.id,
        )
    if pending:
        await callback.message.answer(build_pending_review_block_text(pending))
        await callback.answer()
        return

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
    async with SessionLocal() as session:
        pending = await get_pending_interviewer_reviews_for_tg_user(
            session,
            tg_user_id=callback.from_user.id,
        )
    if pending:
        await callback.message.answer(build_pending_review_block_text(pending))
        await callback.answer()
        return

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
        candidate_username=(message.from_user.username or "no_username"),
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

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    now = utcnow()
    quick = [
        now.replace(hour=19, minute=0, second=0, microsecond=0),
        (now + timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0),
        (now + timedelta(days=2)).replace(hour=18, minute=30, second=0, microsecond=0),
    ]
    kb = InlineKeyboardBuilder()
    for dt in quick:
        slot = dt.strftime("%Y-%m-%d %H:%M")
        kb.button(text=f"🕒 {slot} MSK", callback_data=f"proposal:quick:{proposal_id}:{slot}")
    kb.adjust(1)

    prompt = await callback.message.answer(
        "Введи итоговое время или выбери быстрый слот (MSK):",
        reply_markup=kb.as_markup(),
    )
    await state.update_data(proposal_prompt_message_id=prompt.message_id)
    await callback.answer()


@router.callback_query(F.data.startswith("proposal:quick:"))
async def proposal_quick_time(callback: CallbackQuery, state: FSMContext):
    _, _, proposal_id, slot = callback.data.split(":", 3)
    await state.set_state(ProposalFlow.waiting_final_time)
    await state.update_data(proposal_id=int(proposal_id))

    await callback.message.answer(f"Выбран слот: {slot} MSK. Подтверждаю и отправляю кандидату...")

    normalized = normalize_datetime_input(slot)
    if not normalized:
        await callback.answer("Слот некорректен", show_alert=True)
        return
    if not is_future_slot(normalized):
        await callback.answer("Слот в прошлом. Выбери будущее время.", show_alert=True)
        return

    async with SessionLocal() as session:
        proposal = (await session.execute(select(InterviewProposal).where(InterviewProposal.id == int(proposal_id)))).scalar_one_or_none()
        if not proposal:
            await callback.answer("Заявка не найдена", show_alert=True)
            return
        proposal.options_json = {**(proposal.options_json or {}), "final_time": normalized}
        student = (await session.execute(select(User).where(User.id == proposal.student_id))).scalar_one_or_none()
        await session.commit()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Слот кайф, подтверждаю", callback_data=f"proposal:confirm:{proposal_id}")
    kb.button(text="❌ Не подходит", callback_data=f"proposal:reject:{proposal_id}")
    kb.adjust(1)

    ok, err = await safe_send(
        callback.bot,
        student.tg_user_id,
        "Интервьюер предложил итоговое время:\n"
        f"{normalized} MSK\n"
        "Подтверди слот:",
        reply_markup=kb.as_markup(),
    )
    if not ok:
        await callback.message.answer(f"Не удалось отправить слот кандидату: {err}")
    else:
        await callback.message.answer("Слот отправлен кандидату ✅")

    await state.clear()
    await callback.answer()


@router.message(ProposalFlow.waiting_final_time)
async def proposal_receive_final_time(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    data = await state.get_data()
    prompt_message_id = data.get("proposal_prompt_message_id")
    if (
        prompt_message_id
        and message.reply_to_message
        and message.reply_to_message.message_id != prompt_message_id
    ):
        await state.clear()
        await message.answer(
            "Сбросил ввод слота: пришёл reply к старому сообщению из другого сценария.",
            reply_markup=continue_menu_for_user(message.from_user.id),
        )
        return

    normalized = normalize_datetime_input(raw)
    if not normalized:
        if _looks_like_feedback_text(raw):
            await state.clear()
            await message.answer(
                "Похоже, это оценка/фидбек, а не время. Сбросил ввод слота.",
                reply_markup=continue_menu_for_user(message.from_user.id),
            )
            return
        await message.answer(
            "Неверный формат времени.\n"
            "Поддерживаются форматы:\n"
            "- YYYY-MM-DD HH:MM\n"
            "- DD.MM.YYYY HH:MM\n"
            "- DD.MM HH:MM\n"
            "Все время в MSK."
        )
        return

    if not is_future_slot(normalized):
        await message.answer("Время уже в прошлом. Пришли будущий слот в MSK.")
        return

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

        proposal.options_json = {**(proposal.options_json or {}), "final_time": normalized}
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
        f"{normalized} MSK\n"
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
        pair.last_interview_at = utcnow()

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
