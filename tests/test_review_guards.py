import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.models import CandidateSet, Session, SessionReview, User
from app.db.session import SessionLocal, engine
from app.services.review_guards import (
    build_pending_review_block_text,
    get_pending_interviewer_reviews_for_tg_user,
)
from app.utils.time import utcnow


async def _cleanup(*, user_ids: list[int], set_ids: list[int], session_ids: list[int]):
    async with SessionLocal() as db:
        await db.execute(delete(SessionReview).where(SessionReview.session_id.in_(session_ids)))
        await db.execute(delete(Session).where(Session.id.in_(session_ids)))
        await db.execute(delete(CandidateSet).where(CandidateSet.id.in_(set_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_pending_interviewer_review_detected_and_text_is_actionable():
    await engine.dispose()
    suffix = int(time.time() * 1000) % 1_000_000
    base = utcnow()
    created_user_ids: list[int] = []
    created_set_ids: list[int] = []
    created_session_ids: list[int] = []

    try:
        async with SessionLocal() as db:
            interviewer = User(tg_user_id=9_700_000 + suffix, username=f"int_{suffix}", full_name="Int")
            candidate = User(tg_user_id=9_800_000 + suffix, username=f"cand_{suffix}", full_name="Cand")
            db.add_all([interviewer, candidate])
            await db.flush()
            created_user_ids.extend([interviewer.id, candidate.id])

            set_item = CandidateSet(
                owner_user_id=interviewer.id,
                track_code="livecoding",
                title="Set",
                questions_text="Q",
                status="approved",
            )
            db.add(set_item)
            await db.flush()
            created_set_ids.append(set_item.id)

            sess = Session(
                interviewer_id=interviewer.id,
                student_id=candidate.id,
                track_code="livecoding",
                pack_id=set_item.id,
                starts_at=base - timedelta(hours=2),
                ends_at=base - timedelta(hours=1),
                status="in_progress",
            )
            db.add(sess)
            await db.flush()
            created_session_ids.append(sess.id)

            db.add(
                SessionReview(
                    session_id=sess.id,
                    author_user_id=candidate.id,
                    target_user_id=interviewer.id,
                    author_role="candidate",
                    score=2,
                    comment="ok",
                )
            )
            await db.commit()

            pending = await get_pending_interviewer_reviews_for_tg_user(
                db,
                tg_user_id=interviewer.tg_user_id,
                now=base,
            )
            text = build_pending_review_block_text(pending)

        assert len(pending) == 1
        assert pending[0].session_id == sess.id
        assert "session_id=" in text
        assert "новые собесы недоступны" in text
        assert "Итог: 2.5" in text
    finally:
        if created_user_ids:
            await _cleanup(
                user_ids=created_user_ids,
                set_ids=created_set_ids,
                session_ids=created_session_ids,
            )
        await engine.dispose()
