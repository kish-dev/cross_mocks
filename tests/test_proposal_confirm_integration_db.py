import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.proposals import proposal_confirm, proposal_pick_set
from app.db.models import CandidateSet, InterviewProposal, PairStats, Session, SessionFeedback, SessionReview, User
from app.db.session import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _cleanup_created_rows(*, session_id: int | None, proposal_id: int, set_ids: list[int], student_id: int, interviewer_id: int):
    async with SessionLocal() as db:
        if session_id is not None:
            await db.execute(delete(SessionReview).where(SessionReview.session_id == session_id))
            await db.execute(delete(SessionFeedback).where(SessionFeedback.session_id == session_id))
            await db.execute(delete(Session).where(Session.id == session_id))
        await db.execute(delete(InterviewProposal).where(InterviewProposal.id == proposal_id))

        a, b = sorted((student_id, interviewer_id))
        await db.execute(delete(PairStats).where(PairStats.user_a_id == a, PairStats.user_b_id == b))
        await db.execute(delete(CandidateSet).where(CandidateSet.id.in_(set_ids)))
        await db.execute(delete(User).where(User.id.in_([student_id, interviewer_id])))
        await db.commit()


async def test_proposal_confirm_creates_session_and_marks_accepted(monkeypatch):
    monkeypatch.setattr("app.bot.routers.proposals.sheets_sink.send", lambda *_args, **_kwargs: True)
    suffix = int(time.time() * 1000) % 1000000

    async with SessionLocal() as db:
        student = User(tg_user_id=9_100_000 + suffix, username=f"student_{suffix}", full_name="Student One")
        interviewer = User(tg_user_id=9_200_000 + suffix, username=f"interviewer_{suffix}", full_name="Interviewer One")
        db.add_all([student, interviewer])
        await db.flush()

        set_item = CandidateSet(
            owner_user_id=interviewer.id,
            track_code="livecoding",
            title="LC Set",
            questions_text="Q1",
            status="approved",
        )
        db.add(set_item)
        await db.flush()

        proposal = InterviewProposal(
            student_id=student.id,
            interviewer_id=interviewer.id,
            track_code="livecoding",
            pack_id=set_item.id,
            options_json={"final_time": "2026-12-31 19:00"},
            status="pending",
        )
        db.add(proposal)
        await db.commit()
        proposal_id = proposal.id
        student_tg = student.tg_user_id
        set_id = set_item.id
        student_id = student.id
        interviewer_id = interviewer.id

    callback = SimpleNamespace(
        data=f"proposal:confirm:{proposal_id}",
        from_user=SimpleNamespace(id=student_tg),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
        bot=SimpleNamespace(send_message=AsyncMock()),
    )

    await proposal_confirm(callback)

    async with SessionLocal() as db:
        updated = (await db.execute(select(InterviewProposal).where(InterviewProposal.id == proposal_id))).scalar_one()
        assert updated.status == "accepted"

        sessions = (
            await db.execute(
                select(Session).where(
                    Session.student_id == student_id,
                    Session.interviewer_id == interviewer_id,
                )
            )
        ).scalars().all()
        assert len(sessions) == 1
        created = sessions[0]
        assert created.track_code == "livecoding"
        assert created.status == "scheduled"
        assert created.starts_at == datetime(2026, 12, 31, 19, 0)
        created_session_id = created.id

        pair = (
            await db.execute(
                select(PairStats).where(
                    PairStats.user_a_id == min(student_id, interviewer_id),
                    PairStats.user_b_id == max(student_id, interviewer_id),
                )
            )
        ).scalar_one()
        assert pair.interviews_count == 1

    assert callback.message.answer.await_count >= 1
    assert callback.answer.await_count >= 1

    await _cleanup_created_rows(
        session_id=created_session_id,
        proposal_id=proposal_id,
        set_ids=[set_id],
        student_id=student_id,
        interviewer_id=interviewer_id,
    )


async def test_proposal_confirm_waits_for_interviewer_set_pick_when_multiple_sets(monkeypatch):
    monkeypatch.setattr("app.bot.routers.proposals.sheets_sink.send", lambda *_args, **_kwargs: True)
    suffix = int(time.time() * 1000) % 1000000

    async with SessionLocal() as db:
        student = User(tg_user_id=9_300_000 + suffix, username=f"student_{suffix}", full_name="Student One")
        interviewer = User(tg_user_id=9_400_000 + suffix, username=f"interviewer_{suffix}", full_name="Interviewer One")
        db.add_all([student, interviewer])
        await db.flush()

        set_old = CandidateSet(
            owner_user_id=interviewer.id,
            track_code="livecoding",
            title="LC Set Old",
            questions_text="Q-old",
            status="approved",
        )
        set_new = CandidateSet(
            owner_user_id=interviewer.id,
            track_code="livecoding",
            title="LC Set New",
            questions_text="Q-new",
            status="approved",
        )
        db.add_all([set_old, set_new])
        await db.flush()

        proposal = InterviewProposal(
            student_id=student.id,
            interviewer_id=interviewer.id,
            track_code="livecoding",
            pack_id=set_old.id,
            options_json={"final_time": "2026-12-31 19:00"},
            status="pending",
        )
        db.add(proposal)
        await db.commit()
        proposal_id = proposal.id
        student_tg = student.tg_user_id
        interviewer_tg = interviewer.tg_user_id
        set_old_id = set_old.id
        set_new_id = set_new.id
        student_id = student.id
        interviewer_id = interviewer.id

    bot = SimpleNamespace(send_message=AsyncMock())
    confirm_callback = SimpleNamespace(
        data=f"proposal:confirm:{proposal_id}",
        from_user=SimpleNamespace(id=student_tg),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
        bot=bot,
    )

    await proposal_confirm(confirm_callback)

    async with SessionLocal() as db:
        updated = (await db.execute(select(InterviewProposal).where(InterviewProposal.id == proposal_id))).scalar_one()
        assert updated.status == "pending"
        sessions = (
            await db.execute(
                select(Session).where(
                    Session.student_id == student_id,
                    Session.interviewer_id == interviewer_id,
                )
            )
        ).scalars().all()
        assert len(sessions) == 0

    bot.send_message.assert_awaited()
    sent_tg_ids = [call.args[0] for call in bot.send_message.await_args_list]
    assert interviewer_tg in sent_tg_ids

    pick_callback = SimpleNamespace(
        data=f"proposal:pick_set:{proposal_id}:{set_new_id}",
        from_user=SimpleNamespace(id=interviewer_tg),
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
        bot=bot,
    )

    await proposal_pick_set(pick_callback)

    async with SessionLocal() as db:
        updated = (await db.execute(select(InterviewProposal).where(InterviewProposal.id == proposal_id))).scalar_one()
        assert updated.status == "accepted"
        assert updated.pack_id == set_new_id

        sessions = (
            await db.execute(
                select(Session).where(
                    Session.student_id == student_id,
                    Session.interviewer_id == interviewer_id,
                )
            )
        ).scalars().all()
        assert len(sessions) == 1
        created = sessions[0]
        assert created.pack_id == set_new_id
        created_session_id = created.id

    await _cleanup_created_rows(
        session_id=created_session_id,
        proposal_id=proposal_id,
        set_ids=[set_old_id, set_new_id],
        student_id=student_id,
        interviewer_id=interviewer_id,
    )
