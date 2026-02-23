import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.notifications import build_time_proposal_payload


def test_time_proposal_payload_contains_required_routing_text():
    payload = build_time_proposal_payload(
        interviewer_tg_user_id=100,
        student_tg_user_id=200,
        request_text="завтра после 18",
        track_label="livecoding",
        candidate_username="candidate_one",
    )

    assert payload.interviewer_tg_user_id == 100
    assert payload.student_tg_user_id == 200
    assert "Новый запрос на собес" in payload.interviewer_text
    assert "@candidate_one" in payload.interviewer_text
    assert "livecoding" in payload.interviewer_text
    assert "завтра после 18" in payload.interviewer_text
    assert "MSK" in payload.interviewer_text
    assert payload.student_text == "Запрос отправлен интервьюеру ✅"
