import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.start import (
    candidate_feedback_guide_with_session,
    has_message_url,
    has_session_id_in_message,
    has_session_id_in_reply,
    interviewer_rubric_with_session,
    looks_like_feedback_text,
    reply_context_text,
)


def _msg(
    reply_text: str | None = None,
    reply_caption: str | None = None,
    text: str | None = None,
    caption: str | None = None,
):
    return SimpleNamespace(
        reply_to_message=SimpleNamespace(text=reply_text, caption=reply_caption),
        text=text,
        caption=caption,
    )


def test_reply_context_text_merges_text_and_caption():
    m = _msg("abc", "def")
    assert reply_context_text(m) == "abc\ndef"


def test_has_session_id_in_reply_detects_marker():
    m = _msg("hello\nsession_id=42")
    assert has_session_id_in_reply(m) is True


def test_has_session_id_in_reply_false_without_marker():
    m = _msg("hello", "no marker")
    assert has_session_id_in_reply(m) is False


def test_has_session_id_in_message_detects_marker():
    m = _msg(text="Итог: 2.5\nsession_id=77")
    assert has_session_id_in_message(m) is True


def test_has_session_id_in_message_false_without_marker():
    m = _msg(text="Итог: 2.5")
    assert has_session_id_in_message(m) is False


def test_has_message_url_detects_link():
    m = _msg(text="check https://example.com")
    assert has_message_url(m) is True


def test_has_message_url_false_for_plain_text():
    m = _msg("plain text", text="hello world")
    assert has_message_url(m) is False


def test_guides_include_session_id_marker():
    assert "session_id=42" in candidate_feedback_guide_with_session(42)
    assert "session_id=42" in interviewer_rubric_with_session("livecoding", 42)


def test_looks_like_feedback_text_filter():
    m = _msg(text="Итого 2,5")
    assert looks_like_feedback_text(m) is True

    m.text = "Итого 2,5 session_id=77"
    assert looks_like_feedback_text(m) is False

    m.text = "https://example.com"
    assert looks_like_feedback_text(m) is False
