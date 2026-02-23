import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.scheduling import extract_datetime_slots, can_confirm_slot, normalize_datetime_input


def test_extract_datetime_slots_parses_multiple():
    text = "могу 2026-02-25 19:00 или 2026-02-26 20:30, а также 2026-02-27 18:00"
    slots = extract_datetime_slots(text)
    assert slots == ["2026-02-25 19:00", "2026-02-26 20:30", "2026-02-27 18:00"]


def test_extract_datetime_slots_limit():
    text = " ".join([f"2026-02-{d:02d} 19:00" for d in range(1, 10)])
    slots = extract_datetime_slots(text, limit=5)
    assert len(slots) == 5


def test_can_confirm_slot():
    assert can_confirm_slot("pending", "2026-02-25 19:00") is True
    assert can_confirm_slot("accepted", "2026-02-25 19:00") is False
    assert can_confirm_slot("pending", None) is False


def test_normalize_datetime_input_variants():
    assert normalize_datetime_input("2026-03-01 19:30") == "2026-03-01 19:30"
    assert normalize_datetime_input("01.03.2026 19:30") == "2026-03-01 19:30"
    out = normalize_datetime_input("01.03 19:30")
    assert out.endswith("-03-01 19:30")
    assert normalize_datetime_input("tomorrow evening") is None
