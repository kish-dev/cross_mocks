from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from app.bot.routers.shared import TRACK_LABELS, to_gcal_link
from app.db.models import CandidateSet, Session, User
from app.db.session import SessionLocal
from app.services.stats_analytics import (
    DEFAULT_TRACK_SLICE,
    TRACK_SLICE_LABELS,
    UserStatsSnapshot,
    collect_user_stats,
    format_recent_cards,
    format_track_code,
    format_trend_brief,
    normalize_track_slice,
)
from app.services.stats_plot import build_user_stats_png
from app.utils.time import utcnow

router = Router()


TRACK_SLICE_ORDER = ("all", "theory", "livecoding", "sysdesign", "final")


def _stats_actions_keyboard(track_slice: str) -> InlineKeyboardBuilder:
    normalized = normalize_track_slice(track_slice)
    kb = InlineKeyboardBuilder()
    for key in TRACK_SLICE_ORDER:
        label = TRACK_SLICE_LABELS[key]
        marker = "• " if key == normalized else ""
        kb.button(text=f"{marker}{label}", callback_data=f"stats:user:slice:{key}")
    kb.button(text="📋 Полная статистика", callback_data=f"stats:user:full:{normalized}")
    kb.button(text="📈 График (20)", callback_data=f"stats:user:graph:{normalized}")
    kb.adjust(3, 2, 1, 1)
    return kb


def _render_user_summary(snapshot: UserStatsSnapshot) -> str:
    avg_candidate = f"{snapshot.avg_as_candidate:.2f}" if snapshot.avg_as_candidate is not None else "нет данных"
    avg_interviewer = f"{snapshot.avg_as_interviewer:.2f}" if snapshot.avg_as_interviewer is not None else "нет данных"

    return (
        "Твоя статистика (кратко):\n"
        f"— Срез: {snapshot.track_slice_label}\n"
        f"— Собесов, где ты был интервьюером: {snapshot.interviewer_sessions_count}\n"
        f"— Собесов, где ты был кандидатом: {snapshot.candidate_sessions_count}\n"
        f"— Средняя оценка тебя как кандидата: {avg_candidate}\n"
        f"— Средняя оценка тебя как интервьюера: {avg_interviewer}\n\n"
        f"— Динамика оценок как кандидата (последние 20): {format_trend_brief('оценки', snapshot.trend_as_candidate)}\n"
        f"— Динамика оценок как интервьюера (последние 20): {format_trend_brief('оценки', snapshot.trend_as_interviewer)}"
    )


def _render_breakdown(title: str, rows: list[tuple[str, int, float | None]]) -> str:
    if not rows:
        return f"{title}:\n  • нет данных"
    lines = []
    for track, cnt, avg in rows:
        avg_txt = f"{avg:.2f}" if avg is not None else "нет данных"
        lines.append(f"  • {format_track_code(track)}: собесов — {cnt}, средняя оценка — {avg_txt}")
    return f"{title}:\n" + "\n".join(lines)


def _render_user_full(snapshot: UserStatsSnapshot) -> str:
    return (
        "Твоя статистика (полная):\n\n"
        f"{_render_user_summary(snapshot)}\n\n"
        f"{_render_breakdown('Разбивка как кандидат (внутри среза)', snapshot.candidate_track_breakdown)}\n\n"
        f"{_render_breakdown('Разбивка как интервьюер (внутри среза)', snapshot.interviewer_track_breakdown)}\n\n"
        f"Последние 5 как интервьюер:\n{format_recent_cards(snapshot.recent_as_interviewer, 'кандидат')}\n\n"
        f"Последние 5 как кандидат:\n{format_recent_cards(snapshot.recent_as_candidate, 'интервьюер')}"
    )


def _parse_user_track_slice(callback_data: str, action: str) -> str:
    prefix = f"stats:user:{action}:"
    if callback_data.startswith(prefix):
        return normalize_track_slice(callback_data[len(prefix) :])
    return DEFAULT_TRACK_SLICE


async def _render_upcoming_page(target_message, tg_user_id: int, page: int = 0):
    now = utcnow()
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

        kb = InlineKeyboardBuilder()

        lines = [f"Предстоящие собесы (страница {page + 1}) — время в MSK:"]
        for idx, (s, set_title, student_username, student_tg_id) in enumerate(chunk, start=start + 1):
            is_interviewer = s.interviewer_id == me.id
            role = "интервьюер" if is_interviewer else "кандидат"

            if is_interviewer:
                peer_name = f"@{student_username}" if student_username else f"id:{student_tg_id}"
            else:
                interviewer = (await session.execute(select(User).where(User.id == s.interviewer_id))).scalar_one_or_none()
                peer_name = f"@{interviewer.username}" if interviewer and interviewer.username else f"id:{interviewer.tg_user_id if interviewer else 'n/a'}"

            title_part = f" | набор: {set_title or 'n/a'}" if is_interviewer else ""
            lines.append(
                f"• {idx}. {s.starts_at.strftime('%Y-%m-%d %H:%M')} MSK | {TRACK_LABELS.get(s.track_code, s.track_code)} | {role} | второй: {peer_name}{title_part} (id:{s.id})"
            )

            kb.button(text=f"📅 Календарь {idx}", callback_data=f"upg:cal:{s.id}")
            kb.button(text=f"🗑 Удалить {idx}", callback_data=f"upg:del:{s.id}")

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
        snapshot = await collect_user_stats(session, db_user, track_slice=DEFAULT_TRACK_SLICE)

    await callback.message.answer(
        _render_user_summary(snapshot),
        reply_markup=_stats_actions_keyboard(snapshot.track_slice).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stats:user:slice:"))
async def my_stats_slice(callback: CallbackQuery):
    track_slice = normalize_track_slice(callback.data.split(":")[-1])
    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        snapshot = await collect_user_stats(session, db_user, track_slice=track_slice)

    await callback.message.answer(
        _render_user_summary(snapshot),
        reply_markup=_stats_actions_keyboard(snapshot.track_slice).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "stats:user:full")
@router.callback_query(F.data.startswith("stats:user:full:"))
async def my_stats_full(callback: CallbackQuery):
    track_slice = _parse_user_track_slice(callback.data, "full")
    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        snapshot = await collect_user_stats(session, db_user, track_slice=track_slice)

    await callback.message.answer(_render_user_full(snapshot))
    await callback.answer()


@router.callback_query(F.data == "stats:user:graph")
@router.callback_query(F.data.startswith("stats:user:graph:"))
async def my_stats_graph(callback: CallbackQuery):
    track_slice = _parse_user_track_slice(callback.data, "graph")
    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        snapshot = await collect_user_stats(session, db_user, track_slice=track_slice)

    if not snapshot.candidate_points and not snapshot.interviewer_points:
        await callback.message.answer("Недостаточно данных для графика: нет оценок с итогом (0..3).")
        await callback.answer()
        return

    png = build_user_stats_png(snapshot.candidate_points, snapshot.interviewer_points)
    photo = BufferedInputFile(png, filename="stats_trend.png")
    caption = (
        f"Динамика оценок за последние 20 собесов. Срез: {snapshot.track_slice_label}\n"
        f"Кандидат: {snapshot.trend_as_candidate.trend_label}, confidence={snapshot.trend_as_candidate.confidence_label} (n={snapshot.trend_as_candidate.points_count})\n"
        f"Интервьюер: {snapshot.trend_as_interviewer.trend_label}, confidence={snapshot.trend_as_interviewer.confidence_label} (n={snapshot.trend_as_interviewer.points_count})"
    )
    await callback.message.answer_photo(photo=photo, caption=caption)
    await callback.answer()
