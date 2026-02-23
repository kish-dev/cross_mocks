import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.sheets_sink import SheetsSink


def test_sheets_sink_writes_outbox(tmp_path):
    sink = SheetsSink()
    sink.outbox = tmp_path / "outbox.jsonl"

    ok = sink.send("session_scheduled", {"session_id": 1, "timezone": "MSK"})
    assert ok is True
    lines = sink.outbox.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event_type"] == "session_scheduled"
    assert row["payload"]["timezone"] == "MSK"
