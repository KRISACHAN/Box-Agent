from datetime import datetime, timezone
from uuid import uuid4


def _timestamp(now: datetime | None) -> str:
    value = now if now is not None else datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S")


def new_run_id(now: datetime | None = None) -> str:
    return f"run-{_timestamp(now)}-{uuid4().hex[:8]}"


def new_attempt_id(now: datetime | None = None) -> str:
    return f"attempt-{_timestamp(now)}-{uuid4().hex[:8]}"
