import sys
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.admin_stats import _render_admin_full, _render_admin_summary
from app.bot.routers.stats import _render_user_full, _render_user_summary
from app.services.stats_analytics import SessionCard, TrendMetrics, UserStatsSnapshot


def _snapshot() -> UserStatsSnapshot:
    trend = TrendMetrics(
        points_count=12,
        average=2.2,
        slope=0.04,
        trend_label="рост",
        confidence_label="средняя",
        delta_recent_vs_prev=0.25,
    )
    cards_candidate = [
        SessionCard(
            session_id=101,
            starts_at=datetime(2026, 2, 1, 11, 0),
            track_code="livecoding",
            status="completed",
            interviewer_review_submitted=True,
            candidate_review_submitted=True,
            peer_username="mentor_1",
            peer_tg_user_id=12345,
        )
    ]
    cards_interviewer = [
        SessionCard(
            session_id=202,
            starts_at=datetime(2026, 2, 2, 11, 0),
            track_code="theory",
            status="completed",
            interviewer_review_submitted=True,
            candidate_review_submitted=True,
            peer_username="candidate_1",
            peer_tg_user_id=67890,
        )
    ]
    return UserStatsSnapshot(
        user_id=77,
        username="demo",
        track_slice="all",
        track_slice_label="Общая",
        candidate_sessions_count=3,
        interviewer_sessions_count=4,
        avg_as_candidate=2.3,
        avg_as_interviewer=2.1,
        trend_as_candidate=trend,
        trend_as_interviewer=trend,
        recent_as_candidate=cards_candidate,
        recent_as_interviewer=cards_interviewer,
        candidate_track_breakdown=[("livecoding", 2, 2.5)],
        interviewer_track_breakdown=[("theory", 3, 2.1)],
        candidate_points=[],
        interviewer_points=[],
    )


def test_user_stats_text_contains_required_sections():
    snapshot = _snapshot()
    summary = _render_user_summary(snapshot)
    full = _render_user_full(snapshot)

    assert "как интервьюер" in summary
    assert "как кандидат" in summary
    assert "Срез: Общая" in summary
    assert "Динамика оценок как кандидата" in summary
    assert "надежность —" in summary

    assert "Разбивка как кандидат" in full
    assert "Последние 5 как интервьюер" in full
    assert "session_id=202" in full
    assert "@candidate_1" in full


def test_admin_stats_text_contains_required_sections():
    snapshot = _snapshot()
    summary_student = _render_admin_summary(snapshot, "student")
    full_interviewer = _render_admin_full(snapshot, "interviewer")

    assert "как кандидат" in summary_student
    assert "Динамика:" in summary_student
    assert "Срез: Общая" in summary_student
    assert "как интервьюер, полная" in full_interviewer
    assert "Разбивка по трекам как интервьюер" in full_interviewer
    assert "session_id=202" in full_interviewer
