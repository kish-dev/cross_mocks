import re
from typing import List


SLOT_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\b")


def extract_datetime_slots(text: str, limit: int = 5) -> List[str]:
    if not text:
        return []
    return SLOT_RE.findall(text)[:limit]


def can_confirm_slot(proposal_status: str, final_time: str | None) -> bool:
    return proposal_status == "pending" and bool(final_time)
