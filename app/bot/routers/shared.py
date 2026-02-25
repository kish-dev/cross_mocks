from datetime import datetime
import re
from urllib.parse import urlencode

from app.bot.keyboards.common import main_menu_keyboard
from app.config import settings

TRACK_LABELS = {
    "theory": "theory",
    "sysdesign": "system-design",
    "livecoding": "livecoding",
    "final": "final",
}
TRACK_PURPOSE_LABELS = {
    "theory": "теория",
    "sysdesign": "систем-дизайн",
    "livecoding": "лайвкодинг",
    "final": "финал",
}


def track_purpose_label(track_code: str | None) -> str:
    return TRACK_PURPOSE_LABELS.get(track_code or "unknown", track_code or "unknown")


def format_tg_identity(username: str | None, tg_user_id: int | None) -> str:
    if username and tg_user_id is not None:
        return f"@{username} (id:{tg_user_id})"
    if username:
        return f"@{username}"
    if tg_user_id is not None:
        return f"id:{tg_user_id}"
    return "n/a"


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
        # queue only plain text retries (keyboards are often stale)
        try:
            from app.services.delivery_queue import enqueue
            enqueue(tg_user_id, text)
        except Exception:
            pass
        return False, str(e)


def continue_message_text() -> str:
    return "Гоу дальше 👇 Выбери следующее действие:"


def continue_menu_for_user(tg_user_id: int):
    return main_menu_keyboard(is_admin=tg_user_id in settings.admin_ids)


def parse_feedback_score(text: str) -> float | None:
    normalized = (text or "").lower()
    m = re.search(r"\bитог(?:о)?\b\s*:?\s*([0-3](?:[.,]\d+)?)", normalized)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if value < 0 or value > 3:
        return None
    return value


def extract_feedback_score(text: str) -> int:
    value = parse_feedback_score(text)
    if value is None:
        return 0
    return int(value)
