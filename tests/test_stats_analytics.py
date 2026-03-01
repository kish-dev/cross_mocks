import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.stats_analytics import (
    SessionCard,
    analyze_trend,
    format_session_status,
    linear_regression_slope,
    normalize_track_slice,
    rolling_mean,
    track_code_for_slice,
    track_slice_label,
)


def test_rolling_mean_window_works():
    values = [1.0, 2.0, 3.0, 2.0]
    assert rolling_mean(values, window=2) == [1.0, 1.5, 2.5, 2.5]


def test_linear_regression_slope_detects_growth():
    assert linear_regression_slope([1.0, 1.5, 2.0, 2.5]) > 0


def test_linear_regression_slope_detects_decline():
    assert linear_regression_slope([3.0, 2.5, 2.0, 1.5]) < 0


def test_analyze_trend_handles_insufficient_data():
    summary = analyze_trend([2.0, 2.1])
    assert summary.trend_label == "недостаточно данных"
    assert summary.confidence_label == "низкая"


def test_analyze_trend_confidence_thresholds():
    assert analyze_trend([1.0, 1.2, 1.4]).confidence_label == "хорошая"
    assert analyze_trend([1.0, 1.1, 1.2, 1.3, 1.4, 1.5]).confidence_label == "высокая"


def test_analyze_trend_has_delta_for_enough_points():
    summary = analyze_trend([1.0, 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 1.8, 1.9, 2.0])
    assert summary.delta_recent_vs_prev is not None


def test_track_slice_normalization_and_mapping():
    assert normalize_track_slice("theory") == "theory"
    assert normalize_track_slice("UNKNOWN") == "all"
    assert track_code_for_slice("all") is None
    assert track_code_for_slice("sysdesign") == "sysdesign"
    assert track_slice_label("livecoding") == "Лайвкодинг"


def test_format_session_status_is_human_and_feedback_aware():
    pending = SessionCard(
        session_id=1,
        starts_at=datetime(2026, 1, 1, 10, 0),
        track_code="theory",
        status="in_progress",
        interviewer_review_submitted=False,
        candidate_review_submitted=True,
        peer_username=None,
        peer_tg_user_id=None,
    )
    done = SessionCard(
        session_id=2,
        starts_at=datetime(2026, 1, 1, 11, 0),
        track_code="theory",
        status="completed",
        interviewer_review_submitted=True,
        candidate_review_submitted=True,
        peer_username=None,
        peer_tg_user_id=None,
    )
    assert format_session_status(pending) == "ожидает оценку кандидата интервьюером"
    assert format_session_status(done) == "завершен"
