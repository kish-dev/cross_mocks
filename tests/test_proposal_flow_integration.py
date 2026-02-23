import sys
from pathlib import Path
from datetime import datetime

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.scheduling import can_confirm_slot


def test_proposal_confirm_guard_happy_path():
    assert can_confirm_slot("pending", "2026-02-25 19:00") is True


def test_proposal_confirm_guard_rejects_processed_statuses():
    assert can_confirm_slot("accepted", "2026-02-25 19:00") is False
    assert can_confirm_slot("cancelled", "2026-02-25 19:00") is False


def test_proposal_confirm_guard_requires_time():
    assert can_confirm_slot("pending", None) is False
    assert can_confirm_slot("pending", "") is False
