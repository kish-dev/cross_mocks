import json
from pathlib import Path
from typing import Any

QUEUE_PATH = Path("backups/delivery_queue.jsonl")
QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)


def enqueue(tg_user_id: int, text: str, extra: dict[str, Any] | None = None) -> None:
    payload = {"tg_user_id": tg_user_id, "text": text, "extra": extra or {}}
    with QUEUE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_all() -> list[dict[str, Any]]:
    if not QUEUE_PATH.exists():
        return []
    rows = []
    for line in QUEUE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def replace_all(rows: list[dict[str, Any]]) -> None:
    with QUEUE_PATH.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
