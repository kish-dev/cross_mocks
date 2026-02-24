import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.shared import TRACK_LABELS, extract_feedback_score, parse_feedback_score, to_gcal_link


def test_track_labels_contains_expected_keys():
    assert TRACK_LABELS["theory"] == "theory"
    assert TRACK_LABELS["sysdesign"] == "system-design"
    assert TRACK_LABELS["livecoding"] == "livecoding"
    assert TRACK_LABELS["final"] == "final"


def test_to_gcal_link_contains_dates():
    start = datetime(2026, 2, 25, 19, 0)
    end = datetime(2026, 2, 25, 20, 0)
    link = to_gcal_link("Mock", "details", start, end)
    assert "calendar.google.com" in link
    assert "20260225T190000Z%2F20260225T200000Z" in link


def test_extract_feedback_score_supports_comma_and_optional_colon():
    assert extract_feedback_score("Итог: 3") == 3
    assert extract_feedback_score("Итого 2,5") == 2
    assert extract_feedback_score("без оценки") == 0


def test_parse_feedback_score_requires_keyword_and_range():
    assert parse_feedback_score("Итог: 2.5 комментарий") == 2.5
    assert parse_feedback_score("Итого 3") == 3
    assert parse_feedback_score("оценка 2.5") is None
    assert parse_feedback_score("Итог: 4") is None
