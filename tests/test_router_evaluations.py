import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.evaluations import EvaluationFlow, _build_conduct_sets_keyboard, router


def test_evaluations_router_registered():
    assert router is not None
    assert EvaluationFlow.waiting_scores.state.endswith(":waiting_scores")


def test_conduct_sets_keyboard_has_forward_button_on_first_page():
    rows = [(idx, f"set-{idx}") for idx in range(1, 8)]
    markup, page, total_pages = _build_conduct_sets_keyboard(rows, track="theory", page=0)

    assert page == 0
    assert total_pages == 2

    flat = [button for line in markup.inline_keyboard for button in line]
    callbacks = {button.callback_data for button in flat}
    texts = [button.text for button in flat]

    assert "set-1" in texts
    assert "set-5" in texts
    assert "set-6" not in texts
    assert "conduct_sets_page:theory:1" in callbacks
    assert "conduct_sets_page:theory:0" not in callbacks


def test_conduct_sets_keyboard_clamps_to_last_page_and_has_back_button():
    rows = [(idx, f"set-{idx}") for idx in range(1, 8)]
    markup, page, total_pages = _build_conduct_sets_keyboard(rows, track="theory", page=99)

    assert page == 1
    assert total_pages == 2

    flat = [button for line in markup.inline_keyboard for button in line]
    callbacks = {button.callback_data for button in flat}
    texts = [button.text for button in flat]

    assert "set-6" in texts
    assert "set-7" in texts
    assert "conduct_sets_page:theory:0" in callbacks
    assert "conduct_sets_page:theory:2" not in callbacks
