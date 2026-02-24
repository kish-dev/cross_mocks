from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_stats_router_uses_session_reviews_not_legacy_feedback():
    data = _read("app/bot/routers/stats.py")
    analytics = _read("app/services/stats_analytics.py")
    assert "collect_user_stats" in data
    assert "stats:user:full" in data
    assert "stats:user:graph" in data
    assert "stats:user:slice" in data
    assert "SessionReview" in analytics
    assert "SessionFeedback" not in data
    assert "SessionFeedback" not in analytics
    assert "Session.status != \"cancelled\"" in analytics
    assert "SessionReview.score >= 0" in analytics


def test_admin_stats_router_uses_session_reviews_not_legacy_feedback():
    data = _read("app/bot/routers/admin_stats.py")
    analytics = _read("app/services/stats_analytics.py")
    assert "collect_user_stats" in data
    assert "admin_stats:full" in data
    assert "admin_stats:graph" in data
    assert "admin_stats:slice" in data
    assert "SessionReview" in analytics
    assert "SessionFeedback" not in data
    assert "SessionFeedback" not in analytics
    assert "Session.status != \"cancelled\"" in analytics
    assert "SessionReview.score >= 0" in analytics


def test_submission_approve_sends_continue_cta_to_student():
    data = _read("app/bot/routers/submissions.py")
    assert "continue_message_text" in data
    assert "continue_menu_for_user" in data
    assert "set_submission:approve" in data


def test_start_router_has_plain_feedback_handler():
    data = _read("app/bot/routers/start.py")
    assert "async def feedback_without_reply" in data
    assert "async def meeting_link_via_plain_session_marker" in data
    assert "has_session_id_in_message" in data
    assert "looks_like_feedback_text" in data
    assert "continue_message_text()" in data


def test_submissions_copy_and_handlers_allow_non_reply_resubmit():
    data = _read("app/bot/routers/submissions.py")
    assert "async def resubmit_via_reply" in data
    assert "async def auto_resubmit_latest_changes" in data
    assert "@router.message(StateFilter(None), F.reply_to_message)" in data
    assert "reply-ответом или обычным сообщением в чат" in data


def test_session_start_now_copy_mentions_plain_message_option():
    data = _read("app/bot/routers/sessions.py")
    assert "reply-сообщением или обычным сообщением в чат" in data


def test_proposal_scheduled_message_does_not_use_old_telemost_phrase():
    data = _read("app/bot/routers/proposals.py")
    assert "Сначала создай встречу в Telemost" not in data
    assert "Создай встречу в Telemost и отправь ссылку reply-ответом или обычным сообщением" in data


def test_proposal_has_interviewer_set_pick_flow():
    data = _read("app/bot/routers/proposals.py")
    assert "proposal:pick_set:" in data
    assert "Выбери набор вопросов для этого собеса" in data


def test_find_actions_are_blocked_by_pending_interviewer_review_guard():
    start_data = _read("app/bot/routers/start.py")
    eval_data = _read("app/bot/routers/evaluations.py")
    proposals_data = _read("app/bot/routers/proposals.py")
    assert "get_pending_interviewer_reviews_for_tg_user" in start_data
    assert "build_pending_review_block_text" in start_data
    assert "get_pending_interviewer_reviews_for_tg_user" in eval_data
    assert "build_pending_review_block_text" in eval_data
    assert "get_pending_interviewer_reviews_for_tg_user" in proposals_data
