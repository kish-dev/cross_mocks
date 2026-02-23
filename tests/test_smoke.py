import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_smoke_import():
    import app.main  # noqa
