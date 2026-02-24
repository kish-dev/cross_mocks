from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return naive UTC datetime to match existing DB/application semantics."""
    return datetime.now(UTC).replace(tzinfo=None)
