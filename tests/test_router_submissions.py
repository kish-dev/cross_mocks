import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.submissions import AdminSubmissionFlow, SubmissionFlow, router


def test_submissions_router_registered():
    assert router is not None
    assert SubmissionFlow.waiting_track.state.endswith(":waiting_track")
    assert AdminSubmissionFlow.waiting_comment.state.endswith(":waiting_comment")
