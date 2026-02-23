import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings


class SheetsSink:
    """Mock-first sink with file outbox. Real Google Sheets adapter TODO."""

    def __init__(self) -> None:
        self.outbox = Path(settings.SHEETS_OUTBOX_PATH)
        self.outbox.parent.mkdir(parents=True, exist_ok=True)

    def _append_outbox(self, payload: dict[str, Any]) -> None:
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def send(self, event_type: str, payload: dict[str, Any]) -> bool:
        envelope = {
            "ts": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "payload": payload,
            "sheet_id": settings.GOOGLE_SHEET_ID,
            "mode": "mock" if not settings.GOOGLE_SHEET_ID or not settings.GOOGLE_SHEETS_CREDENTIALS_JSON else "todo_real",
        }
        # Always persist, then (future) best-effort deliver to Sheets API.
        self._append_outbox(envelope)
        return True


sheets_sink = SheetsSink()
