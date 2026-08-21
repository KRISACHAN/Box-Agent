"""Complete-record readers and a simple unified timeline."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\S+")


def _record(source: str, index: int, payload: Any, timestamp: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"source": source, "index": index, "timestamp": timestamp, "payload": payload, **extra}


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("timestamp", "time", "created_at", "started_at", "finished_at"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            return candidate
    message = value.get("message")
    return _timestamp(message) if isinstance(message, dict) else None


def read_jsonl(path: Path, source: str = "record") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return records
    for index, line in enumerate(lines, 1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            records.append(_record(source, index, line, parse_error=str(error)))
            continue
        records.append(_record(source, index, payload, _timestamp(payload)))
    return records


def read_stderr(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    records = []
    for index, line in enumerate(lines, 1):
        folded = line.casefold()
        if "timeout" in folded:
            category = "timeout"
        elif "error" in folded:
            category = "error"
        elif "warning" in folded or "warn" in folded:
            category = "warning"
        else:
            category = "log"
        match = TIMESTAMP_RE.search(line)
        records.append(_record("stderr", index, line, match.group(0) if match else None, category=category))
    return records


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {"data_missing_or_invalid": str(error)}


def source_records(attempt_dir: Path, source: str) -> list[dict[str, Any]]:
    if source == "acp":
        return read_jsonl(attempt_dir / "protocol.jsonl", "acp")
    if source == "agent":
        records: list[dict[str, Any]] = []
        for path in sorted((attempt_dir / "agent").glob("*.jsonl")):
            records.extend(read_jsonl(path, "agent"))
        return records
    if source == "process":
        return read_jsonl(attempt_dir / "process.jsonl", "process") + read_stderr(attempt_dir / "stderr.log")
    if source == "files":
        return [
            _record("files", index, {"file": name, "content": _read_json(attempt_dir / name)})
            for index, name in enumerate(("files-before.json", "files-after.json", "artifacts.json"), 1)
        ]
    if source == "completeness":
        return [_record("completeness", 1, _read_json(attempt_dir / "completeness.json"))]
    raise ValueError(source)


def _sort_key(record: dict[str, Any]) -> tuple[int, float, str, int]:
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str):
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            return (0, parsed.timestamp(), str(record["source"]), int(record["index"]))
        except ValueError:
            pass
    return (1, float("inf"), str(record["source"]), int(record["index"]))


def unified_timeline(attempt_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in ("acp", "agent", "process", "files", "completeness"):
        records.extend(source_records(attempt_dir, source))
    return sorted(records, key=_sort_key)


def page_records(records: Sequence[dict[str, Any]], page: int, per_page: int = 200) -> tuple[list[dict[str, Any]], int | None]:
    page = max(1, page)
    start = (page - 1) * per_page
    stop = start + per_page
    return list(records[start:stop]), page + 1 if stop < len(records) else None
