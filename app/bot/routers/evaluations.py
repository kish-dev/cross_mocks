from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select

from app.bot.keyboards.common import evaluation_keyboard, track_keyboard
from app.bot.routers.shared import TRACK_LABELS, continue_menu_for_user, continue_message_text
from app.config import settings
from app.db.models import CandidateSet, QuickEvaluation, User
from app.db.session import SessionLocal
from app.services.review_guards import (
    build_pending_review_block_text,
    get_pending_interviewer_reviews_for_tg_user,
)

router = Router()
CONDUCT_SETS_PAGE_SIZE = 5


class EvaluationFlow(StatesGroup):
    waiting_candidate_pick = State()
    waiting_candidate_username = State()
    waiting_scores = State()
    waiting_comment = State()


def _build_conduct_sets_keyboard(rows: list[tuple[int, str]], track: str, page: int):
    max_page = max((len(rows) - 1) // CONDUCT_SETS_PAGE_SIZE, 0)
    page = min(max(page, 0), max_page)

    start = page * CONDUCT_SETS_PAGE_SIZE
    page_rows = rows[start:start + CONDUCT_SETS_PAGE_SIZE]

    kb = InlineKeyboardBuilder()
    for set_id, title in page_rows:
        kb.button(text=title, callback_data=f"conduct_set:{set_id}")

    nav_buttons = 0
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"conduct_sets_page:{track}:{page - 1}")
        nav_buttons += 1
    if page < max_page:
        kb.button(text="Вперёд ➡️", callback_data=f"conduct_sets_page:{track}:{page + 1}")
        nav_buttons += 1

    layout = [1] * len(page_rows)
    if nav_buttons:
        layout.append(nav_buttons)
    kb.adjust(*layout)

    return kb.as_markup(), page, max_page + 1


@router.callback_query(F.data == "menu:find_student")
async def find_student(callback: CallbackQuery):
    async with SessionLocal() as session:
        pending = await get_pending_interviewer_reviews_for_tg_user(
            session,
            tg_user_id=callback.from_user.id,
        )
    if pending:
        await callback.message.answer(build_pending_review_block_text(pending))
        await callback.answer()
        return
    await callback.message.answer("Выбери трек собеса:", reply_markup=track_keyboard("conduct_track"))
    await callback.answer()


@router.callback_query(F.data.startswith("conduct_track:"))
async def conduct_track(callback: CallbackQuery):
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

        rows = (
            await session.execute(
                select(CandidateSet.id, CandidateSet.title)
                .where(
                    CandidateSet.track_code == track,
                    CandidateSet.status == "approved",
                    CandidateSet.owner_user_id == db_user.id,
                )
                .order_by(CandidateSet.created_at.desc())
                .limit(100)
            )
        ).all()

    if not rows:
        await callback.message.answer(
            "У тебя нет одобренных наборов для этого трека.\n"
            "Сначала отправь и получи approve хотя бы для одного набора."
        )
        await callback.answer()
        return

    markup, page, total_pages = _build_conduct_sets_keyboard(rows, track, page=0)
    text = "Выбери набор собесов, который ты проводишь:"
    if total_pages > 1:
        text += f"\nСтраница {page + 1}/{total_pages}"

    await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("conduct_sets_page:"))
async def conduct_sets_page(callback: CallbackQuery):
    try:
        _, track, page_raw = callback.data.split(":", 2)
        page = int(page_raw)
    except (ValueError, IndexError):
        await callback.answer("Некорректная страница", show_alert=True)
        return

    async with SessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not db_user:
            await callback.answer("Сначала нажми /start", show_alert=True)
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
                .limit(100)
            )
        ).all()

    if not rows:
        await callback.answer("Наборы не найдены", show_alert=True)
        return

    markup, page, total_pages = _build_conduct_sets_keyboard(rows, track, page=page)
    text = "Выбери набор собесов, который ты проводишь:"
    if total_pages > 1:
        text += f"\nСтраница {page + 1}/{total_pages}"

    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("conduct_set:"))
async def conduct_set(callback: CallbackQuery):
    set_id = int(callback.data.split(":")[-1])
    async with SessionLocal() as session:
        set_item = (await session.execute(select(CandidateSet).where(CandidateSet.id == set_id))).scalar_one_or_none()
        if not set_item:
            await callback.answer("Набор не найден", show_alert=True)
            return

    await callback.message.answer(
        f"Набор: {set_item.title}\n"
        f"Трек: {TRACK_LABELS.get(set_item.track_code, set_item.track_code)}\n\n"
        "Теперь выбери кандидата:",
        reply_markup=evaluation_keyboard(set_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("eval:start:"))
async def eval_start(callback: CallbackQuery, state: FSMContext):
    async with SessionLocal() as session:
        pending = await get_pending_interviewer_reviews_for_tg_user(
            session,
            tg_user_id=callback.from_user.id,
        )
    if pending:
        await callback.message.answer(build_pending_review_block_text(pending))
        await callback.answer()
        return

    set_id = int(callback.data.split(":")[-1])

    async with SessionLocal() as session:
        set_item = (await session.execute(select(CandidateSet).where(CandidateSet.id == set_id))).scalar_one_or_none()
        if not set_item:
            await callback.answer("Набор не найден", show_alert=True)
            return
        me = (await session.execute(select(User).where(User.tg_user_id == callback.from_user.id))).scalar_one_or_none()
        if not me or me.id != set_item.owner_user_id:
            await callback.answer("Это не твой набор", show_alert=True)
            return

    await state.set_state(EvaluationFlow.waiting_candidate_pick)
    await state.update_data(set_id=set_id, track_code=set_item.track_code)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="Выбрать из последних кандидатов", callback_data="eval:candidate:last")
    kb.button(text="Ввести @username вручную", callback_data="eval:candidate:manual")
    kb.adjust(1)

    await callback.message.answer("Кого оцениваем?", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("eval:candidate:"))
async def eval_candidate_pick(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[-1]
    if mode == "manual":
        await state.set_state(EvaluationFlow.waiting_candidate_username)
        await callback.message.answer("Введи @username кандидата:")
        await callback.answer()
        return

    await state.set_state(EvaluationFlow.waiting_candidate_username)
    await callback.message.answer("Введи @username кандидата (быстрый ввод):")
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
    else:
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
        else:
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
            score=int(round(avg * 100)),
            comment=f"avg={avg}; verdict={verdict}; rubric={data.get('rubric')}; note={comment}",
        )
        session.add(item)

        candidate_user = (await session.execute(select(User).where(func.lower(User.username) == candidate_username.lower()))).scalar_one_or_none()
        if candidate_user:
            candidate_tg_user_id = candidate_user.tg_user_id

        await session.commit()

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
    await message.answer(
        continue_message_text(),
        reply_markup=continue_menu_for_user(message.from_user.id),
    )
