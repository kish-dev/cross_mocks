import re
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.routers.shared import (
    TRACK_LABELS,
    candidate_feedback_guide,
    continue_menu_for_user,
    continue_message_text,
    interviewer_rubric_text,
    parse_feedback_score,
    safe_send,
)
from app.config import settings
from app.db.models import Session, SessionReview, User
from app.db.session import SessionLocal
from app.services.sheets_sink import sheets_sink
from app.utils.time import utcnow

router = Router()


class SessionClosureFlow(StatesGroup):
    waiting_comment = State()


async def _try_forward_meeting_link(message: Message) -> bool:
    content = (message.text or message.caption or "").strip()
    m = re.search(r"https?://\S+", content)
    if not m:
        return False
    meeting_url = m.group(0)

    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not me:
            return False

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
            return False

        candidate = (await session.execute(select(User).where(User.id == s.student_id))).scalar_one_or_none()
        if not candidate:
            return False

        s.meeting_url = meeting_url
        await session.commit()

    await safe_send(
        message.bot,
        candidate.tg_user_id,
        "Ссылка на созвон от интервьюера:\n"
        f"{meeting_url}\n"
        f"session_id={s.id}",
    )
    await safe_send(
        message.bot,
        candidate.tg_user_id,
        "Как оценить качество собеса и общение:\n"
        f"{candidate_feedback_guide()}\n"
        f"session_id={s.id}",
    )
    await safe_send(
        message.bot,
        me.tg_user_id,
        "Гайд оценки для интервьюера:\n"
        f"{interviewer_rubric_text(s.track_code)}\n"
        f"session_id={s.id}",
    )
    await message.answer(f"Ссылку отправил кандидату для session_id={s.id} ✅")
    return True


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

        s.starts_at = utcnow()
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
            "Ссылка на созвон появится, когда интервьюер создаст её. Отправлю новым сообщением.",
        )

        if not (ok1 and ok2 and ok3):
            await callback.message.answer(
                "⚠️ Не все служебные сообщения доставлены.\n"
                f"second={ok1} ({err1})\ninterviewer={ok2} ({err2})\nstudent={ok3} ({err3})"
            )

    await callback.answer()


@router.message(SessionClosureFlow.waiting_comment)
async def session_review_comment(message: Message, state: FSMContext):
    if await _try_forward_meeting_link(message):
        return

    comment = (message.text or "").strip()
    if not comment:
        await message.answer("Комментарий не может быть пустым")
        return

    data = await state.get_data()
    session_id = data.get("session_id")
    role = data.get("role")

    parsed_score = parse_feedback_score(comment)
    if parsed_score is None:
        await message.answer(
            "Фидбек не сохранён.\n"
            "Добавь итог в формате: «Итог: 2.5» (число от 0 до 3) и комментарий."
        )
        return
    score = int(parsed_score)

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

        reviews = (await session.execute(select(SessionReview).where(SessionReview.session_id == session_id))).scalars().all()

        await session.commit()

        await state.clear()
        await message.answer("Фидбек сохранен ✅")
        await message.answer(
            continue_message_text(),
            reply_markup=continue_menu_for_user(message.from_user.id),
        )

        if len(reviews) >= 2:
            s.status = "completed"
            await session.commit()

            users = {
                u.id: u
                for u in (await session.execute(select(User).where(User.id.in_([s.student_id, s.interviewer_id])))).scalars().all()
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
