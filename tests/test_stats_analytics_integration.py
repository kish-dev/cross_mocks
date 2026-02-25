import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.models import CandidateSet, Session, SessionReview, User
from app.db.session import SessionLocal, engine
from app.services.stats_analytics import collect_user_stats, format_recent_cards
from app.utils.time import utcnow


async def _cleanup_stats_rows(*, user_ids: list[int], set_ids: list[int], session_ids: list[int]):
    async with SessionLocal() as db:
        await db.execute(delete(SessionReview).where(SessionReview.session_id.in_(session_ids)))
        await db.execute(delete(Session).where(Session.id.in_(session_ids)))
        await db.execute(delete(CandidateSet).where(CandidateSet.id.in_(set_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_collect_user_stats_recent_cards_and_peers():
    await engine.dispose()
    suffix = int(time.time() * 1000) % 1_000_000
    base = utcnow()
    created_user_ids: list[int] = []
    created_set_ids: list[int] = []
    created_session_ids: list[int] = []

    try:
        async with SessionLocal() as db:
            main_user = User(tg_user_id=7_100_000 + suffix, username=f"main_{suffix}", full_name="Main")
            peer_interviewer = User(
                tg_user_id=7_200_000 + suffix, username=f"peer_int_{suffix}", full_name="Peer Int"
            )
            peer_candidate = User(
                tg_user_id=7_300_000 + suffix, username=f"peer_cand_{suffix}", full_name="Peer Cand"
            )
            db.add_all([main_user, peer_interviewer, peer_candidate])
            await db.flush()
            created_user_ids.extend([main_user.id, peer_interviewer.id, peer_candidate.id])

            interviewer_set = CandidateSet(
                owner_user_id=peer_interviewer.id,
                track_code="livecoding",
                title="Set A",
                questions_text="Q",
                status="approved",
            )
            candidate_set = CandidateSet(
                owner_user_id=main_user.id,
                track_code="theory",
                title="Set B",
                questions_text="Q",
                status="approved",
            )
            db.add_all([interviewer_set, candidate_set])
            await db.flush()
            created_set_ids.extend([interviewer_set.id, candidate_set.id])

            candidate_sessions = []
            interviewer_sessions = []
            for idx in range(6):
                candidate_sessions.append(
                    Session(
                        interviewer_id=peer_interviewer.id,
                        student_id=main_user.id,
                        track_code="livecoding",
                        pack_id=interviewer_set.id,
                        starts_at=base - timedelta(days=idx + 1),
                        ends_at=base - timedelta(days=idx + 1) + timedelta(hours=1),
                        status="completed",
                    )
                )
                interviewer_sessions.append(
                    Session(
                        interviewer_id=main_user.id,
                        student_id=peer_candidate.id,
                        track_code="theory",
                        pack_id=candidate_set.id,
                        starts_at=base - timedelta(days=idx + 10),
                        ends_at=base - timedelta(days=idx + 10) + timedelta(hours=1),
                        status="completed",
                    )
                )
            db.add_all(candidate_sessions + interviewer_sessions)
            await db.flush()
            created_session_ids.extend([s.id for s in candidate_sessions + interviewer_sessions])

            candidate_scores = [1, 2, 3, 2, 0, 3]
            interviewer_scores = [2, 2, 1, 3, 2, 3]
            for idx, sess in enumerate(candidate_sessions):
                db.add(
                    SessionReview(
                        session_id=sess.id,
                        author_user_id=peer_interviewer.id,
                        target_user_id=main_user.id,
                        author_role="interviewer",
                        score=candidate_scores[idx],
                        comment="ok",
                    )
                )
            for idx, sess in enumerate(interviewer_sessions):
                db.add(
                    SessionReview(
                        session_id=sess.id,
                        author_user_id=peer_candidate.id,
                        target_user_id=main_user.id,
                        author_role="candidate",
                        score=interviewer_scores[idx],
                        comment="ok",
                    )
                )

            await db.commit()

            snapshot = await collect_user_stats(db, main_user, now=base)
            snapshot_live = await collect_user_stats(db, main_user, now=base, track_slice="livecoding")
            snapshot_theory = await collect_user_stats(db, main_user, now=base, track_slice="theory")
            snapshot_unknown = await collect_user_stats(db, main_user, now=base, track_slice="whatever")

        assert snapshot.candidate_sessions_count == 6
        assert snapshot.interviewer_sessions_count == 6
        assert snapshot.avg_as_candidate == pytest.approx(11 / 6, rel=1e-6)
        assert snapshot.avg_as_interviewer == pytest.approx(13 / 6, rel=1e-6)

        assert len(snapshot.recent_as_candidate) == 5
        assert len(snapshot.recent_as_interviewer) == 5
        assert snapshot.recent_as_candidate[0].peer_username == f"peer_int_{suffix}"
        assert snapshot.recent_as_interviewer[0].peer_username == f"peer_cand_{suffix}"

        assert len(snapshot.candidate_points) == 6
        assert len(snapshot.interviewer_points) == 6
        assert snapshot.track_slice == "all"

        assert snapshot_live.track_slice == "livecoding"
        assert snapshot_live.candidate_sessions_count == 6
        assert snapshot_live.interviewer_sessions_count == 0
        assert len(snapshot_live.recent_as_candidate) == 5
        assert len(snapshot_live.recent_as_interviewer) == 0

        assert snapshot_theory.track_slice == "theory"
        assert snapshot_theory.candidate_sessions_count == 0
        assert snapshot_theory.interviewer_sessions_count == 6
        assert len(snapshot_theory.recent_as_candidate) == 0
        assert len(snapshot_theory.recent_as_interviewer) == 5

        assert snapshot_unknown.track_slice == "all"
        assert snapshot_unknown.candidate_sessions_count == snapshot.candidate_sessions_count

        rendered_candidate = format_recent_cards(snapshot.recent_as_candidate, "интервьюер")
        rendered_interviewer = format_recent_cards(snapshot.recent_as_interviewer, "кандидат")
        assert "session_id=" in rendered_candidate
        assert "статус:" in rendered_candidate
        assert f"@peer_int_{suffix}" in rendered_candidate
        assert f"@peer_cand_{suffix}" in rendered_interviewer
        assert "completed" not in rendered_candidate
        assert "|" not in rendered_candidate
        assert "|" not in rendered_interviewer
    finally:
        if created_user_ids:
            await _cleanup_stats_rows(
                user_ids=created_user_ids,
                set_ids=created_set_ids,
                session_ids=created_session_ids,
            )
        await engine.dispose()


@pytest.mark.asyncio
async def test_collect_user_stats_empty_data():
    await engine.dispose()
    suffix = int(time.time() * 1000) % 1_000_000
    created_user_id: int | None = None

    try:
        async with SessionLocal() as db:
            user = User(tg_user_id=7_900_000 + suffix, username=f"empty_{suffix}", full_name="Empty")
            db.add(user)
            await db.commit()
            created_user_id = user.id

            snapshot = await collect_user_stats(db, user, now=utcnow())

        assert snapshot.candidate_sessions_count == 0
        assert snapshot.interviewer_sessions_count == 0
        assert snapshot.avg_as_candidate is None
        assert snapshot.avg_as_interviewer is None
        assert snapshot.trend_as_candidate.points_count == 0
        assert snapshot.trend_as_candidate.trend_label == "недостаточно данных"
        assert snapshot.recent_as_candidate == []
        assert snapshot.recent_as_interviewer == []
        assert format_recent_cards(snapshot.recent_as_candidate, "интервьюер") == "  • нет данных"
    finally:
        if created_user_id is not None:
            async with SessionLocal() as db:
                await db.execute(delete(User).where(User.id == created_user_id))
                await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_collect_user_stats_recent_not_empty_for_scheduled_future_sessions():
    await engine.dispose()
    suffix = int(time.time() * 1000) % 1_000_000
    base = utcnow()
    created_user_ids: list[int] = []
    created_set_ids: list[int] = []
    created_session_ids: list[int] = []

    try:
        async with SessionLocal() as db:
            interviewer = User(tg_user_id=8_100_000 + suffix, username=f"int_{suffix}", full_name="Int")
            candidate = User(tg_user_id=8_200_000 + suffix, username=f"cand_{suffix}", full_name="Cand")
            db.add_all([interviewer, candidate])
            await db.flush()
            created_user_ids.extend([interviewer.id, candidate.id])

            set_item = CandidateSet(
                owner_user_id=interviewer.id,
                track_code="final",
                title="Future Set",
                questions_text="Q",
                status="approved",
            )
            db.add(set_item)
            await db.flush()
            created_set_ids.append(set_item.id)

            future_session = Session(
                interviewer_id=interviewer.id,
                student_id=candidate.id,
                track_code="final",
                pack_id=set_item.id,
                starts_at=base + timedelta(days=3),
                ends_at=base + timedelta(days=3, hours=1),
                status="scheduled",
            )
            db.add(future_session)
            await db.flush()
            created_session_ids.append(future_session.id)
            await db.commit()

            interviewer_snapshot = await collect_user_stats(db, interviewer, now=base)
            candidate_snapshot = await collect_user_stats(db, candidate, now=base)

        assert interviewer_snapshot.interviewer_sessions_count == 1
        assert candidate_snapshot.candidate_sessions_count == 1
        assert len(interviewer_snapshot.recent_as_interviewer) == 1
        assert len(candidate_snapshot.recent_as_candidate) == 1
        assert interviewer_snapshot.recent_as_interviewer[0].session_id == future_session.id
        assert candidate_snapshot.recent_as_candidate[0].session_id == future_session.id
    finally:
        if created_user_ids:
            await _cleanup_stats_rows(
                user_ids=created_user_ids,
                set_ids=created_set_ids,
                session_ids=created_session_ids,
            )
        await engine.dispose()
