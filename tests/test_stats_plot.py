import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.stats_analytics import ScorePoint
from app.services.stats_plot import build_user_stats_png


def test_build_user_stats_png_returns_png_bytes():
    base = datetime(2026, 1, 1, 10, 0)
    points = [
        ScorePoint(session_id=1, starts_at=base, track_code="livecoding", score=1.0),
        ScorePoint(session_id=2, starts_at=base + timedelta(days=1), track_code="livecoding", score=2.0),
        ScorePoint(session_id=3, starts_at=base + timedelta(days=2), track_code="livecoding", score=2.5),
    ]

    png = build_user_stats_png(points, points)
    assert isinstance(png, bytes)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
