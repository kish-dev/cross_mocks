import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.admin_stats import AdminStatsFlow, router


def test_admin_stats_router_registered():
    assert router is not None
    assert AdminStatsFlow.waiting_nickname.state.endswith(":waiting_nickname")
