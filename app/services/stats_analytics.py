from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.routers.shared import TRACK_LABELS
from app.db.models import Session, SessionReview, User
from app.utils.time import utcnow

DEFAULT_TRACK_SLICE = "all"
TRACK_SLICE_TO_CODE: dict[str, str | None] = {
    "all": None,
    "theory": "theory",
    "livecoding": "livecoding",
    "sysdesign": "sysdesign",
    "final": "final",
}
TRACK_SLICE_LABELS: dict[str, str] = {
    "all": "Общая",
    "theory": "Теория",
    "livecoding": "Лайвкодинг",
    "sysdesign": "Систем-дизайн",
    "final": "Финал",
}


@dataclass
class SessionCard:
    session_id: int
    starts_at: datetime
    track_code: str
    status: str
    interviewer_review_submitted: bool
    candidate_review_submitted: bool
    peer_username: str | None
    peer_tg_user_id: int | None


@dataclass
class ScorePoint:
    session_id: int
    starts_at: datetime
    track_code: str
    score: float


@dataclass
class TrendMetrics:
    points_count: int
    average: float | None
    slope: float
    trend_label: str
    confidence_label: str
    delta_recent_vs_prev: float | None


@dataclass
class UserStatsSnapshot:
    user_id: int
    username: str | None
    track_slice: str
    track_slice_label: str
    candidate_sessions_count: int
    interviewer_sessions_count: int
    avg_as_candidate: float | None
    avg_as_interviewer: float | None
    trend_as_candidate: TrendMetrics
    trend_as_interviewer: TrendMetrics
    recent_as_candidate: list[SessionCard]
    recent_as_interviewer: list[SessionCard]
    candidate_track_breakdown: list[tuple[str, int, float | None]]
    interviewer_track_breakdown: list[tuple[str, int, float | None]]
    candidate_points: list[ScorePoint]
    interviewer_points: list[ScorePoint]


def rolling_mean(values: list[float], window: int = 5) -> list[float]:
    if window <= 1 or not values:
        return list(values)
    out: list[float] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        out.append(sum(values[start : i + 1]) / (i - start + 1))
    return out


def linear_regression_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
    return numer / denom


def _confidence_label(points_count: int) -> str:
    if points_count >= 15:
        return "высокая"
    if points_count >= 8:
        return "средняя"
    return "низкая"


def _trend_label(slope: float, points_count: int) -> str:
    if points_count < 4:
        return "недостаточно данных"
    if slope > 0.03:
        return "рост"
    if slope < -0.03:
        return "снижение"
    return "стабильность"


def analyze_trend(values: list[float]) -> TrendMetrics:
    n = len(values)
    avg = mean(values) if values else None
    slope = linear_regression_slope(values)
    delta: float | None = None
    if n >= 10:
        recent = values[-5:]
        prev = values[-10:-5]
        if prev:
            delta = mean(recent) - mean(prev)
    return TrendMetrics(
        points_count=n,
        average=avg,
        slope=slope,
        trend_label=_trend_label(slope, n),
        confidence_label=_confidence_label(n),
        delta_recent_vs_prev=delta,
    )


def _merge_track_stats(
    count_rows: list[tuple[str, int]],
    avg_rows: list[tuple[str, float | None]],
) -> list[tuple[str, int, float | None]]:
    count_map = {track: count for track, count in count_rows}
    avg_map = {track: avg for track, avg in avg_rows}
    keys = sorted(set(count_map.keys()) | set(avg_map.keys()))
    return [(track, count_map.get(track, 0), avg_map.get(track)) for track in keys]


def format_track_code(track_code: str | None) -> str:
    return TRACK_LABELS.get(track_code or "unknown", track_code or "unknown")


def normalize_track_slice(track_slice: str | None) -> str:
    key = (track_slice or DEFAULT_TRACK_SLICE).strip().lower()
    return key if key in TRACK_SLICE_TO_CODE else DEFAULT_TRACK_SLICE


def track_code_for_slice(track_slice: str | None) -> str | None:
    return TRACK_SLICE_TO_CODE[normalize_track_slice(track_slice)]


def track_slice_label(track_slice: str | None) -> str:
    normalized = normalize_track_slice(track_slice)
    return TRACK_SLICE_LABELS.get(normalized, f"Неизвестный срез ({normalized})")


def format_peer(peer_username: str | None, peer_tg_user_id: int | None) -> str:
    if peer_username:
        return f"@{peer_username}"
    if peer_tg_user_id is not None:
        return f"id:{peer_tg_user_id}"
    return "n/a"


def format_recent_cards(cards: list[SessionCard], peer_role: str) -> str:
    if not cards:
        return "  • нет данных"
    return "\n".join(
        (
            f"  • {c.starts_at.strftime('%Y-%m-%d %H:%M')} MSK"
            f" | {format_track_code(c.track_code)}"
            f" | {peer_role}: {format_peer(c.peer_username, c.peer_tg_user_id)}"
            f" | статус: {format_session_status(c)} | session_id={c.session_id}"
        )
        for c in cards
    )


def format_trend_brief(label: str, trend: TrendMetrics) -> str:
    if trend.points_count == 0:
        return f"{label}: пока нет данных."
    delta_txt = "пока недостаточно данных"
    if trend.delta_recent_vs_prev is not None:
        sign = "+" if trend.delta_recent_vs_prev >= 0 else ""
        delta_txt = f"{sign}{trend.delta_recent_vs_prev:.2f}"
    avg_txt = f"{trend.average:.2f}" if trend.average is not None else "нет данных"
    return (
        f"{label}: {trend.trend_label}; "
        f"средняя оценка — {avg_txt}; "
        f"изменение последних 5 к предыдущим 5 — {delta_txt}; "
        f"надежность — {trend.confidence_label} (оценок: {trend.points_count})"
    )


def format_session_status(card: SessionCard) -> str:
    if card.status == "cancelled":
        return "отменен"
    if card.interviewer_review_submitted and card.candidate_review_submitted:
        return "завершен"
    if card.interviewer_review_submitted and not card.candidate_review_submitted:
        return "ожидает отзыв кандидата"
    if not card.interviewer_review_submitted and card.candidate_review_submitted:
        return "ожидает оценку кандидата интервьюером"
    if card.status == "scheduled":
        return "запланирован"
    if card.status == "in_progress":
        return "в процессе"
    if card.status == "completed":
        return "завершен"
    return card.status


async def collect_user_stats(
    session: AsyncSession,
    db_user: User,
    *,
    now: datetime | None = None,
    recent_limit: int = 5,
    trend_window: int = 20,
    track_slice: str = DEFAULT_TRACK_SLICE,
) -> UserStatsSnapshot:
    _ = now or utcnow()
    normalized_slice = normalize_track_slice(track_slice)
    track_code_filter = track_code_for_slice(normalized_slice)

    candidate_count_filters = [
        Session.student_id == db_user.id,
        Session.status != "cancelled",
    ]
    interviewer_count_filters = [
        Session.interviewer_id == db_user.id,
        Session.status != "cancelled",
    ]
    if track_code_filter is not None:
        candidate_count_filters.append(Session.track_code == track_code_filter)
        interviewer_count_filters.append(Session.track_code == track_code_filter)

    candidate_sessions_count = (
        await session.execute(
            select(func.count(Session.id)).where(*candidate_count_filters)
        )
    ).scalar_one()

    interviewer_sessions_count = (
        await session.execute(
            select(func.count(Session.id)).where(*interviewer_count_filters)
        )
    ).scalar_one()

    candidate_avg_filters = [
        SessionReview.target_user_id == db_user.id,
        SessionReview.author_role == "interviewer",
        SessionReview.score >= 0,
        SessionReview.score <= 3,
        Session.status != "cancelled",
    ]
    interviewer_avg_filters = [
        SessionReview.target_user_id == db_user.id,
        SessionReview.author_role == "candidate",
        SessionReview.score >= 0,
        SessionReview.score <= 3,
        Session.status != "cancelled",
    ]
    if track_code_filter is not None:
        candidate_avg_filters.append(Session.track_code == track_code_filter)
        interviewer_avg_filters.append(Session.track_code == track_code_filter)

    avg_as_candidate = (
        await session.execute(
            select(func.avg(SessionReview.score))
            .join(Session, Session.id == SessionReview.session_id)
            .where(*candidate_avg_filters)
        )
    ).scalar_one()

    avg_as_interviewer = (
        await session.execute(
            select(func.avg(SessionReview.score))
            .join(Session, Session.id == SessionReview.session_id)
            .where(*interviewer_avg_filters)
        )
    ).scalar_one()

    recent_candidate_filters = [
        Session.student_id == db_user.id,
        Session.status != "cancelled",
    ]
    recent_interviewer_filters = [
        Session.interviewer_id == db_user.id,
        Session.status != "cancelled",
    ]
    if track_code_filter is not None:
        recent_candidate_filters.append(Session.track_code == track_code_filter)
        recent_interviewer_filters.append(Session.track_code == track_code_filter)

    recent_as_candidate_rows = (
        await session.execute(
            select(Session)
            .where(*recent_candidate_filters)
            .order_by(Session.starts_at.desc())
            .limit(recent_limit)
        )
    ).scalars().all()

    recent_as_interviewer_rows = (
        await session.execute(
            select(Session)
            .where(*recent_interviewer_filters)
            .order_by(Session.starts_at.desc())
            .limit(recent_limit)
        )
    ).scalars().all()

    peer_ids = {s.interviewer_id for s in recent_as_candidate_rows}
    peer_ids.update(s.student_id for s in recent_as_interviewer_rows)
    peers = {
        u.id: u
        for u in (await session.execute(select(User).where(User.id.in_(peer_ids)))).scalars().all()
    }

    recent_session_ids = [s.id for s in recent_as_candidate_rows + recent_as_interviewer_rows]
    review_pairs = (
        await session.execute(
            select(SessionReview.session_id, SessionReview.author_user_id).where(
                SessionReview.session_id.in_(recent_session_ids)
            )
        )
    ).all() if recent_session_ids else []
    reviewed_by: dict[int, set[int]] = {}
    for session_id, author_user_id in review_pairs:
        reviewed_by.setdefault(session_id, set()).add(author_user_id)

    recent_as_candidate = [
        SessionCard(
            session_id=s.id,
            starts_at=s.starts_at,
            track_code=s.track_code,
            status=s.status,
            interviewer_review_submitted=s.interviewer_id in reviewed_by.get(s.id, set()),
            candidate_review_submitted=s.student_id in reviewed_by.get(s.id, set()),
            peer_username=peers.get(s.interviewer_id).username if peers.get(s.interviewer_id) else None,
            peer_tg_user_id=peers.get(s.interviewer_id).tg_user_id if peers.get(s.interviewer_id) else None,
        )
        for s in recent_as_candidate_rows
    ]

    recent_as_interviewer = [
        SessionCard(
            session_id=s.id,
            starts_at=s.starts_at,
            track_code=s.track_code,
            status=s.status,
            interviewer_review_submitted=s.interviewer_id in reviewed_by.get(s.id, set()),
            candidate_review_submitted=s.student_id in reviewed_by.get(s.id, set()),
            peer_username=peers.get(s.student_id).username if peers.get(s.student_id) else None,
            peer_tg_user_id=peers.get(s.student_id).tg_user_id if peers.get(s.student_id) else None,
        )
        for s in recent_as_interviewer_rows
    ]

    candidate_points_filters = [
        SessionReview.target_user_id == db_user.id,
        SessionReview.author_role == "interviewer",
        SessionReview.score >= 0,
        SessionReview.score <= 3,
        Session.status != "cancelled",
    ]
    interviewer_points_filters = [
        SessionReview.target_user_id == db_user.id,
        SessionReview.author_role == "candidate",
        SessionReview.score >= 0,
        SessionReview.score <= 3,
        Session.status != "cancelled",
    ]
    if track_code_filter is not None:
        candidate_points_filters.append(Session.track_code == track_code_filter)
        interviewer_points_filters.append(Session.track_code == track_code_filter)

    candidate_points_rows = (
        await session.execute(
            select(SessionReview.score, Session.starts_at, Session.track_code, Session.id)
            .join(Session, Session.id == SessionReview.session_id)
            .where(*candidate_points_filters)
            .order_by(Session.starts_at.desc())
            .limit(trend_window)
        )
    ).all()

    interviewer_points_rows = (
        await session.execute(
            select(SessionReview.score, Session.starts_at, Session.track_code, Session.id)
            .join(Session, Session.id == SessionReview.session_id)
            .where(*interviewer_points_filters)
            .order_by(Session.starts_at.desc())
            .limit(trend_window)
        )
    ).all()

    candidate_points = [
        ScorePoint(session_id=sid, starts_at=starts_at, track_code=track_code, score=float(score))
        for score, starts_at, track_code, sid in reversed(candidate_points_rows)
    ]

    interviewer_points = [
        ScorePoint(session_id=sid, starts_at=starts_at, track_code=track_code, score=float(score))
        for score, starts_at, track_code, sid in reversed(interviewer_points_rows)
    ]

    candidate_track_count_filters = [
        Session.student_id == db_user.id,
        Session.status != "cancelled",
    ]
    candidate_track_avg_filters = [
        SessionReview.target_user_id == db_user.id,
        SessionReview.author_role == "interviewer",
        SessionReview.score >= 0,
        SessionReview.score <= 3,
        Session.status != "cancelled",
    ]
    interviewer_track_count_filters = [
        Session.interviewer_id == db_user.id,
        Session.status != "cancelled",
    ]
    interviewer_track_avg_filters = [
        SessionReview.target_user_id == db_user.id,
        SessionReview.author_role == "candidate",
        SessionReview.score >= 0,
        SessionReview.score <= 3,
        Session.status != "cancelled",
    ]
    if track_code_filter is not None:
        candidate_track_count_filters.append(Session.track_code == track_code_filter)
        candidate_track_avg_filters.append(Session.track_code == track_code_filter)
        interviewer_track_count_filters.append(Session.track_code == track_code_filter)
        interviewer_track_avg_filters.append(Session.track_code == track_code_filter)

    candidate_track_count_rows = (
        await session.execute(
            select(Session.track_code, func.count(Session.id))
            .where(*candidate_track_count_filters)
            .group_by(Session.track_code)
        )
    ).all()
    candidate_track_avg_rows = (
        await session.execute(
            select(Session.track_code, func.avg(SessionReview.score))
            .join(Session, Session.id == SessionReview.session_id)
            .where(*candidate_track_avg_filters)
            .group_by(Session.track_code)
        )
    ).all()

    interviewer_track_count_rows = (
        await session.execute(
            select(Session.track_code, func.count(Session.id))
            .where(*interviewer_track_count_filters)
            .group_by(Session.track_code)
        )
    ).all()
    interviewer_track_avg_rows = (
        await session.execute(
            select(Session.track_code, func.avg(SessionReview.score))
            .join(Session, Session.id == SessionReview.session_id)
            .where(*interviewer_track_avg_filters)
            .group_by(Session.track_code)
        )
    ).all()

    return UserStatsSnapshot(
        user_id=db_user.id,
        username=db_user.username,
        track_slice=normalized_slice,
        track_slice_label=track_slice_label(normalized_slice),
        candidate_sessions_count=int(candidate_sessions_count),
        interviewer_sessions_count=int(interviewer_sessions_count),
        avg_as_candidate=float(avg_as_candidate) if avg_as_candidate is not None else None,
        avg_as_interviewer=float(avg_as_interviewer) if avg_as_interviewer is not None else None,
        trend_as_candidate=analyze_trend([p.score for p in candidate_points]),
        trend_as_interviewer=analyze_trend([p.score for p in interviewer_points]),
        recent_as_candidate=recent_as_candidate,
        recent_as_interviewer=recent_as_interviewer,
        candidate_track_breakdown=_merge_track_stats(candidate_track_count_rows, candidate_track_avg_rows),
        interviewer_track_breakdown=_merge_track_stats(interviewer_track_count_rows, interviewer_track_avg_rows),
        candidate_points=candidate_points,
        interviewer_points=interviewer_points,
    )
