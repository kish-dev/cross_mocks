import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.routers.stats import router


def test_stats_router_registered():
    assert router is not None
