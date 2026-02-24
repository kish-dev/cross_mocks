import re

from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from app.config import settings
from app.db.models import User, Session, SessionReview
from app.db.session import SessionLocal
from app.repositories.users import UsersRepo
from app.bot.keyboards.common import (
    main_menu_keyboard,
    track_keyboard,
)
from app.bot.routers.shared import (
    candidate_feedback_guide,
    continue_menu_for_user,
    continue_message_text,
    interviewer_rubric_text,
    parse_feedback_score,
    safe_send,
)
from app.services.review_guards import (
    build_pending_review_block_text,
    get_pending_interviewer_reviews_for_tg_user,
)

router = Router()


def message_context_text(message: Message) -> str:
    return ((message.text or "") + "\n" + (message.caption or "")).strip()


def reply_context_text(message: Message) -> str:
    reply = message.reply_to_message
    if not reply:
        return ""
    return ((reply.text or "") + "\n" + (reply.caption or "")).strip()


def extract_session_id(text: str) -> int | None:
    match = re.search(r"session_id=(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def has_session_id_in_reply(message: Message) -> bool:
    return extract_session_id(reply_context_text(message)) is not None


def has_session_id_in_message(message: Message) -> bool:
    return extract_session_id(message_context_text(message)) is not None


def has_message_url(message: Message) -> bool:
    return bool(re.search(r"https?://\S+", message_context_text(message)))


def candidate_feedback_guide_with_session(session_id: int) -> str:
    return (
        "Как оценить качество собеса и общение:\n"
        f"{candidate_feedback_guide()}\n"
        f"session_id={session_id}"
    )


def interviewer_rubric_with_session(track_code: str, session_id: int) -> str:
    return (
        "Гайд оценки для интервьюера:\n"
        f"{interviewer_rubric_text(track_code)}\n"
        f"session_id={session_id}"
    )


WELCOME = (
    "Привет! Я бот для парных мок-собеседований.\n\n"
    "Что я делаю:\n"
    "— помогаю найти пару для мок-собеса\n"
    "— фиксирую результаты и прогресс\n"
    "— собираю статистику по прохождениям и проведениям\n\n"
    "Выбери действие ниже ⤵️"
)

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


async def _handle_session_context_message(message: Message, session_id: int):
    content = message_context_text(message)
    url_match = re.search(r"https?://\S+", content)
    me = None
    s = None

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
                        candidate_feedback_guide_with_session(session_id)
                    )
                except Exception:
                    pass

            try:
                await message.bot.send_message(
                    me.tg_user_id,
                    interviewer_rubric_with_session(s.track_code, session_id)
                )
            except Exception:
                pass
            return

        # 2) Participant sends feedback with session_id (reply or plain message)
        if me.id in {s.student_id, s.interviewer_id} and content:
            parsed_score = parse_feedback_score(content)
            if parsed_score is None:
                await message.answer(
                    "Фидбек не сохранён.\n"
                    "Добавь итог в формате: «Итог: 2.5» (число от 0 до 3) и комментарий."
                )
                return
            target_id = s.interviewer_id if me.id == s.student_id else s.student_id
            role = "candidate" if me.id == s.student_id else "interviewer"
            score = int(parsed_score)

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
            await message.answer(
                continue_message_text(),
                reply_markup=continue_menu_for_user(message.from_user.id),
            )
            return

    # If there is URL but sender is not interviewer of this session
    if url_match and me and s and me.id != s.interviewer_id:
        await message.answer("Ссылку на созвон может отправить только интервьюер.")


@router.message(F.reply_to_message, has_session_id_in_reply)
async def meeting_link_via_reply(message: Message):
    session_id = extract_session_id(reply_context_text(message))
    if session_id is None:
        return
    await _handle_session_context_message(message, session_id)


@router.message(StateFilter(None), has_session_id_in_message)
async def meeting_link_via_plain_session_marker(message: Message):
    session_id = extract_session_id(message_context_text(message))
    if session_id is None:
        return
    await _handle_session_context_message(message, session_id)


def looks_like_feedback_text(message: Message) -> bool:
    content = message_context_text(message).lower()
    if not content:
        return False
    if content.startswith("/"):
        return False
    if extract_session_id(content) is not None:
        return False
    if re.search(r"https?://\S+", content):
        return False
    return bool(re.search(r"(итог|оцен|балл|фидбек)", content))


@router.message(StateFilter(None), looks_like_feedback_text)
async def feedback_without_reply(message: Message):
    content = message_context_text(message)
    parsed_score = parse_feedback_score(content)
    if parsed_score is None:
        await message.answer(
            "Фидбек не сохранён.\n"
            "Добавь итог в формате: «Итог: 2.5» (число от 0 до 3) и комментарий."
        )
        return

    async with SessionLocal() as session:
        me = (await session.execute(select(User).where(User.tg_user_id == message.from_user.id))).scalar_one_or_none()
        if not me:
            return

        candidates = (
            await session.execute(
                select(Session)
                .where(
                    ((Session.student_id == me.id) | (Session.interviewer_id == me.id)),
                    Session.status.in_(["in_progress", "completed"]),
                )
                .order_by(Session.created_at.desc())
                .limit(5)
            )
        ).scalars().all()

        target_session = None
        for s in candidates:
            existing = (
                await session.execute(
                    select(SessionReview).where(
                        SessionReview.session_id == s.id,
                        SessionReview.author_user_id == me.id,
                    )
                )
            ).scalar_one_or_none()
            if not existing:
                target_session = s
                break

        if not target_session:
            return

        target_id = target_session.interviewer_id if me.id == target_session.student_id else target_session.student_id
        role = "candidate" if me.id == target_session.student_id else "interviewer"
        score = int(parsed_score)

        session.add(
            SessionReview(
                session_id=target_session.id,
                author_user_id=me.id,
                target_user_id=target_id,
                author_role=role,
                score=score,
                comment=content,
            )
        )
        await session.commit()

    await message.answer(f"Фидбек сохранен ✅ (session_id={target_session.id})")
    await message.answer(
        continue_message_text(),
        reply_markup=continue_menu_for_user(message.from_user.id),
    )


@router.message(StateFilter(None), has_message_url)
async def meeting_link_without_reply(message: Message, state: FSMContext):
    # interviewer can send telemost link without reply; bot routes to candidate of nearest active session
    current_state = await state.get_state()
    if current_state is not None:
        return

    content = message_context_text(message)
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
        candidate_feedback_guide_with_session(s.id)
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
        interviewer_rubric_with_session(s.track_code, s.id)
    )


@router.callback_query(F.data == "menu:find_interviewer")
async def find_interviewer(callback: CallbackQuery):
    async with SessionLocal() as session:
        pending = await get_pending_interviewer_reviews_for_tg_user(
            session,
            tg_user_id=callback.from_user.id,
        )
    if pending:
        await callback.message.answer(build_pending_review_block_text(pending))
        await callback.answer()
        return
    await callback.message.answer("Выбери тему собеса, который хочешь пройти:", reply_markup=track_keyboard("pass_track"))
    await callback.answer()
