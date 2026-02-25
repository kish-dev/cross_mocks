import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.proposals import _looks_like_feedback_text, proposal_quick_time, proposal_receive_final_time


class DummyState:
    def __init__(self, data=None):
        self._data = data or {}
        self.clear = AsyncMock()
        self.set_state = AsyncMock()
        self.update_data = AsyncMock()

    async def get_data(self):
        return dict(self._data)


@pytest.mark.asyncio
async def test_proposal_receive_final_time_clears_state_on_feedback_like_text():
    state = DummyState(data={"proposal_id": 1, "proposal_prompt_message_id": 123})
    message = SimpleNamespace(
        text="Итого 2,5",
        reply_to_message=None,
        from_user=SimpleNamespace(id=100),
        answer=AsyncMock(),
    )

    await proposal_receive_final_time(message, state)

    state.clear.assert_awaited_once()
    assert message.answer.await_count == 1
    assert "Сбросил ввод слота" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_proposal_receive_final_time_clears_state_on_reply_to_stale_prompt():
    state = DummyState(data={"proposal_id": 1, "proposal_prompt_message_id": 500})
    message = SimpleNamespace(
        text="2026-12-31 19:00",
        reply_to_message=SimpleNamespace(message_id=111),
        from_user=SimpleNamespace(id=100),
        answer=AsyncMock(),
    )

    await proposal_receive_final_time(message, state)

    state.clear.assert_awaited_once()
    assert message.answer.await_count == 1
    assert "старому сообщению" in message.answer.await_args.args[0]


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, proposal, student, interviewer):
        self._proposal = proposal
        self._student = student
        self._interviewer = interviewer
        self._n = 0

    async def execute(self, _query):
        self._n += 1
        if self._n == 1:
            return _FakeResult(self._proposal)
        if self._n == 2:
            return _FakeResult(self._student)
        return _FakeResult(self._interviewer)

    async def commit(self):
        return None


class _FakeSessionLocal:
    def __init__(self, proposal, student, interviewer):
        self._proposal = proposal
        self._student = student
        self._interviewer = interviewer

    async def __aenter__(self):
        return _FakeSession(self._proposal, self._student, self._interviewer)

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_feedback_text_detector():
    assert _looks_like_feedback_text("Итого 2,5") is True
    assert _looks_like_feedback_text("Оценка 3") is True
    assert _looks_like_feedback_text("2026-12-31 19:00") is False


@pytest.mark.asyncio
async def test_proposal_quick_time_clears_state_after_success(monkeypatch):
    proposal = SimpleNamespace(id=1, options_json={}, student_id=11, interviewer_id=12, track_code="final")
    student = SimpleNamespace(tg_user_id=777, username="student_1")
    interviewer = SimpleNamespace(tg_user_id=778, username="interviewer_1")
    monkeypatch.setattr("app.bot.routers.proposals.normalize_datetime_input", lambda _raw: "2026-12-31 19:00")
    monkeypatch.setattr("app.bot.routers.proposals.is_future_slot", lambda _raw: True)
    monkeypatch.setattr("app.bot.routers.proposals.safe_send", AsyncMock(return_value=(True, "")))
    monkeypatch.setattr("app.bot.routers.proposals.SessionLocal", lambda: _FakeSessionLocal(proposal, student, interviewer))

    state = DummyState()
    callback = SimpleNamespace(
        data="proposal:quick:1:2026-12-31 19:00",
        message=SimpleNamespace(answer=AsyncMock()),
        bot=SimpleNamespace(),
        answer=AsyncMock(),
    )

    await proposal_quick_time(callback, state)

    state.clear.assert_awaited_once()
    callback.answer.assert_awaited_once()
