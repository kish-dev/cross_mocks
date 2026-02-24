import re
from datetime import datetime
from typing import List

from app.utils.time import utcnow


SLOT_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\b")


def extract_datetime_slots(text: str, limit: int = 5) -> List[str]:
    if not text:
        return []
    return SLOT_RE.findall(text)[:limit]


def normalize_datetime_input(text: str, now: datetime | None = None) -> str | None:
    """Accepts:
    - YYYY-MM-DD HH:MM
    - DD.MM.YYYY HH:MM
    - DD.MM HH:MM (current year)
    Returns normalized YYYY-MM-DD HH:MM or None.
    """
    t = (text or "").strip()
    if not t:
        return None

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}", t):
        return t

    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2})", t)
    if m:
        d, mo, y, hm = m.groups()
        return f"{y}-{mo}-{d} {hm}"

    m2 = re.fullmatch(r"(\d{2})\.(\d{2})\s+(\d{2}:\d{2})", t)
    if m2:
        d, mo, hm = m2.groups()
        year = (now or utcnow()).year
        return f"{year}-{mo}-{d} {hm}"

    return None


def can_confirm_slot(proposal_status: str, final_time: str | None) -> bool:
    return proposal_status == "pending" and bool(final_time)


def is_future_slot(slot: str, now: datetime | None = None) -> bool:
    try:
        dt = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return dt > (now or utcnow())
