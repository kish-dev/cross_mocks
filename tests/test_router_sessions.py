import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.sessions import SessionClosureFlow, router


def test_sessions_router_registered():
    assert router is not None
    assert SessionClosureFlow.waiting_comment.state.endswith(":waiting_comment")
