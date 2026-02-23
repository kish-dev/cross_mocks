import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services import delivery_queue as dq


def test_delivery_queue_roundtrip(tmp_path):
    dq.QUEUE_PATH = tmp_path / "q.jsonl"
    dq.enqueue(1, "hello")
    dq.enqueue(2, "world")
    rows = dq.load_all()
    assert len(rows) == 2
    assert rows[0]["tg_user_id"] == 1
    dq.replace_all(rows[:1])
    rows2 = dq.load_all()
    assert len(rows2) == 1
    assert rows2[0]["text"] == "hello"
