from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from app.bot.keyboards.common import admin_role_keyboard
from app.config import settings
from app.db.models import User
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

router = Router()
TRACK_SLICE_ORDER = ("all", "theory", "livecoding", "sysdesign", "final")


class AdminStatsFlow(StatesGroup):
    waiting_nickname = State()


def _admin_stats_actions_keyboard(user_id: int, mode: str, track_slice: str) -> InlineKeyboardBuilder:
    normalized = normalize_track_slice(track_slice)
    kb = InlineKeyboardBuilder()
    for key in TRACK_SLICE_ORDER:
        label = TRACK_SLICE_LABELS[key]
        marker = "• " if key == normalized else ""
        kb.button(text=f"{marker}{label}", callback_data=f"admin_stats:slice:{user_id}:{mode}:{key}")
    kb.button(text="📋 Полная статистика", callback_data=f"admin_stats:full:{user_id}:{mode}:{normalized}")
    kb.button(text="📈 График (20)", callback_data=f"admin_stats:graph:{user_id}:{mode}:{normalized}")
    kb.adjust(3, 2, 1, 1)
    return kb


def _render_breakdown(title: str, rows: list[tuple[str, int, float | None]]) -> str:
    if not rows:
        return f"{title}:\n  • нет данных"
    lines = []
    for track, cnt, avg in rows:
        avg_txt = f"{avg:.2f}" if avg is not None else "нет данных"
        lines.append(f"  • {format_track_code(track)}: собесов — {cnt}, средняя оценка — {avg_txt}")
    return f"{title}:\n" + "\n".join(lines)


def _render_admin_summary(snapshot: UserStatsSnapshot, mode: str) -> str:
    username = snapshot.username or f"id:{snapshot.user_id}"
    if mode == "student":
        avg = f"{snapshot.avg_as_candidate:.2f}" if snapshot.avg_as_candidate is not None else "нет данных"
        return (
            f"Админ-статистика для @{username} (как кандидат):\n"
            f"— Срез: {snapshot.track_slice_label}\n"
            f"— Всего собесов в роли кандидата: {snapshot.candidate_sessions_count}\n"
            f"— Средняя оценка как кандидата: {avg}"
        ) + f"\n— Динамика: {format_trend_brief('кандидат', snapshot.trend_as_candidate)}"

    avg = f"{snapshot.avg_as_interviewer:.2f}" if snapshot.avg_as_interviewer is not None else "нет данных"
    return (
        f"Админ-статистика для @{username} (как интервьюер):\n"
        f"— Срез: {snapshot.track_slice_label}\n"
        f"— Всего собесов в роли интервьюера: {snapshot.interviewer_sessions_count}\n"
        f"— Средняя оценка как интервьюера: {avg}"
    ) + f"\n— Динамика: {format_trend_brief('интервьюер', snapshot.trend_as_interviewer)}"


def _render_admin_full(snapshot: UserStatsSnapshot, mode: str) -> str:
    username = snapshot.username or f"id:{snapshot.user_id}"
    if mode == "student":
        return (
            f"Админ-статистика для @{username} (как кандидат, полная):\n\n"
            f"{_render_admin_summary(snapshot, mode)}\n\n"
            f"{_render_breakdown('Разбивка по трекам как кандидат (внутри среза)', snapshot.candidate_track_breakdown)}\n\n"
            f"Последние 5 сессий как кандидат:\n{format_recent_cards(snapshot.recent_as_candidate, 'интервьюер')}"
        )

    return (
        f"Админ-статистика для @{username} (как интервьюер, полная):\n\n"
        f"{_render_admin_summary(snapshot, mode)}\n\n"
        f"{_render_breakdown('Разбивка по трекам как интервьюер (внутри среза)', snapshot.interviewer_track_breakdown)}\n\n"
        f"Последние 5 сессий как интервьюер:\n{format_recent_cards(snapshot.recent_as_interviewer, 'кандидат')}"
    )


def _parse_admin_payload(callback_data: str, action: str) -> tuple[int, str, str] | None:
    prefix = f"admin_stats:{action}:"
    if not callback_data.startswith(prefix):
        return None
    payload = callback_data[len(prefix) :].split(":")
    if len(payload) == 2:
        user_id_str, mode = payload
        track_slice = DEFAULT_TRACK_SLICE
    elif len(payload) >= 3:
        user_id_str, mode, track_slice = payload[0], payload[1], payload[2]
    else:
        return None
    try:
        user_id = int(user_id_str)
    except ValueError:
        return None
    return user_id, mode, normalize_track_slice(track_slice)


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
        db_user = (await session.execute(select(User).where(func.lower(User.username) == username.lower()))).scalar_one_or_none()
        if not db_user:
            await callback.message.answer(f"Пользователь @{username} не найден в базе.")
            await callback.answer()
            return

        snapshot = await collect_user_stats(session, db_user, track_slice=DEFAULT_TRACK_SLICE)

    await state.clear()
    await callback.message.answer(
        _render_admin_summary(snapshot, mode),
        reply_markup=_admin_stats_actions_keyboard(db_user.id, mode, snapshot.track_slice).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stats:slice:"))
async def admin_stats_slice(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    parsed = _parse_admin_payload(callback.data, "slice")
    if not parsed:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user_id, mode, track_slice = parsed

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        snapshot = await collect_user_stats(session, db_user, track_slice=track_slice)

    await callback.message.answer(
        _render_admin_summary(snapshot, mode),
        reply_markup=_admin_stats_actions_keyboard(db_user.id, mode, snapshot.track_slice).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stats:full:"))
async def admin_stats_full(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    parsed = _parse_admin_payload(callback.data, "full")
    if not parsed:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user_id, mode, track_slice = parsed

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        snapshot = await collect_user_stats(session, db_user, track_slice=track_slice)

    await callback.message.answer(_render_admin_full(snapshot, mode))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_stats:graph:"))
async def admin_stats_graph(callback: CallbackQuery):
    if callback.from_user.id not in settings.admin_ids:
        await callback.answer("Только для админа", show_alert=True)
        return

    parsed = _parse_admin_payload(callback.data, "graph")
    if not parsed:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user_id, mode, track_slice = parsed

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        snapshot = await collect_user_stats(session, db_user, track_slice=track_slice)

    if mode == "student":
        candidate_points = snapshot.candidate_points
        interviewer_points = []
    else:
        candidate_points = []
        interviewer_points = snapshot.interviewer_points

    if not candidate_points and not interviewer_points:
        await callback.message.answer("Недостаточно данных для графика: нет оценок с итогом (0..3).")
        await callback.answer()
        return

    png = build_user_stats_png(candidate_points, interviewer_points)
    photo = BufferedInputFile(png, filename="admin_stats_trend.png")
    await callback.message.answer_photo(
        photo=photo,
        caption=(
            f"График пользователя @{snapshot.username or snapshot.user_id}.\n"
            f"Режим: {'кандидат' if mode == 'student' else 'интервьюер'}\n"
            f"Срез: {snapshot.track_slice_label}"
        ),
    )
    await callback.answer()
