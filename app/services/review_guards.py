from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.bot.routers.shared import TRACK_LABELS
from app.db.models import Session, SessionReview, User
from app.utils.time import utcnow


@dataclass
class PendingInterviewerReview:
    session_id: int
    starts_at: datetime
    track_code: str
    session_status: str
    interviewer_user_id: int
    interviewer_tg_user_id: int
    candidate_username: str | None
    candidate_tg_user_id: int | None


def _track_label(track_code: str) -> str:
    return TRACK_LABELS.get(track_code, track_code)


def _pending_interviewer_review_stmt(now: datetime):
    interviewer = aliased(User)
    candidate = aliased(User)
    interviewer_review_exists = exists(
        select(SessionReview.id).where(
            SessionReview.session_id == Session.id,
            SessionReview.author_user_id == Session.interviewer_id,
            SessionReview.author_role == "interviewer",
        )
    )
    return (
        select(
            Session.id,
            Session.starts_at,
            Session.track_code,
            Session.status,
            interviewer.id,
            interviewer.tg_user_id,
            candidate.username,
            candidate.tg_user_id,
        )
        .join(interviewer, interviewer.id == Session.interviewer_id)
        .join(candidate, candidate.id == Session.student_id)
        .where(
            Session.status.in_(["in_progress", "completed"]),
            Session.starts_at <= now,
            ~interviewer_review_exists,
        )
        .order_by(Session.starts_at.asc())
    )


async def get_pending_interviewer_reviews(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> list[PendingInterviewerReview]:
    now = now or utcnow()
    rows = (await session.execute(_pending_interviewer_review_stmt(now))).all()
    return [
        PendingInterviewerReview(
            session_id=session_id,
            starts_at=starts_at,
            track_code=track_code,
            session_status=status,
            interviewer_user_id=interviewer_user_id,
            interviewer_tg_user_id=interviewer_tg_user_id,
            candidate_username=candidate_username,
            candidate_tg_user_id=candidate_tg_user_id,
        )
        for (
            session_id,
            starts_at,
            track_code,
            status,
            interviewer_user_id,
            interviewer_tg_user_id,
            candidate_username,
            candidate_tg_user_id,
        ) in rows
    ]


async def get_pending_interviewer_reviews_for_tg_user(
    session: AsyncSession,
    *,
    tg_user_id: int,
    now: datetime | None = None,
) -> list[PendingInterviewerReview]:
    now = now or utcnow()
    interviewer = aliased(User)
    candidate = aliased(User)
    interviewer_review_exists = exists(
        select(SessionReview.id).where(
            SessionReview.session_id == Session.id,
            SessionReview.author_user_id == Session.interviewer_id,
            SessionReview.author_role == "interviewer",
        )
    )
    rows = (
        await session.execute(
            select(
                Session.id,
                Session.starts_at,
                Session.track_code,
                Session.status,
                interviewer.id,
                interviewer.tg_user_id,
                candidate.username,
                candidate.tg_user_id,
            )
            .join(interviewer, interviewer.id == Session.interviewer_id)
            .join(candidate, candidate.id == Session.student_id)
            .where(
                interviewer.tg_user_id == tg_user_id,
                Session.status.in_(["in_progress", "completed"]),
                Session.starts_at <= now,
                ~interviewer_review_exists,
            )
            .order_by(Session.starts_at.asc())
        )
    ).all()
    return [
        PendingInterviewerReview(
            session_id=session_id,
            starts_at=starts_at,
            track_code=track_code,
            session_status=status,
            interviewer_user_id=interviewer_user_id,
            interviewer_tg_user_id=interviewer_tg_user_id,
            candidate_username=candidate_username,
            candidate_tg_user_id=candidate_tg_user_id,
        )
        for (
            session_id,
            starts_at,
            track_code,
            status,
            interviewer_user_id,
            interviewer_tg_user_id,
            candidate_username,
            candidate_tg_user_id,
        ) in rows
    ]


def build_pending_review_block_text(items: list[PendingInterviewerReview], *, limit: int = 3) -> str:
    if not items:
        return ""
    lines = [
        "Сначала оставь отзыв на кандидата по незавершенному собесу.",
        "Пока отзыв не отправлен, новые собесы недоступны и как интервьюеру, и как кандидату.",
        "",
        "Нужно закрыть:",
    ]
    for item in items[:limit]:
        candidate = f"@{item.candidate_username}" if item.candidate_username else f"id:{item.candidate_tg_user_id}"
        lines.append(
            f"• session_id={item.session_id} | {_track_label(item.track_code)} | "
            f"{item.starts_at.strftime('%Y-%m-%d %H:%M')} MSK | кандидат: {candidate}"
        )
    lines.extend(
        [
            "",
            "Как закрыть: отправь отзыв в ответ на сообщение с этим session_id.",
            "Формат: «Итог: 2.5 ...» (число от 0 до 3).",
        ]
    )
    return "\n".join(lines)


def build_pending_review_reminder_text(item: PendingInterviewerReview) -> str:
    candidate = f"@{item.candidate_username}" if item.candidate_username else f"id:{item.candidate_tg_user_id}"
    return (
        "📝 Напоминание: нужно оставить отзыв на кандидата.\n"
        f"session_id={item.session_id}\n"
        f"Трек: {_track_label(item.track_code)}\n"
        f"Кандидат: {candidate}\n"
        "Пока отзыв не отправлен, новые собесы недоступны.\n\n"
        "Ответь на это сообщение:\n"
        "Итог: 2.5\n"
        "Короткий комментарий."
    )
