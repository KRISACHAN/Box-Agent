import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from acp_eval.ids import new_attempt_id, new_run_id
from acp_eval import SCHEMA_VERSION
from acp_eval.storage import (
    append_jsonl,
    append_raw,
    atomic_write_json,
    sha256_file,
)


def test_ids_use_utc_timestamp_and_hex_suffix() -> None:
    now = datetime(2026, 8, 21, 0, 12, 34, tzinfo=timezone.utc)

    run_id = new_run_id(now)
    attempt_id = new_attempt_id(now)

    assert re.fullmatch(r"run-20260821T001234-[0-9a-f]{8}", run_id)
    assert re.fullmatch(r"attempt-20260821T001234-[0-9a-f]{8}", attempt_id)


def test_atomic_write_json_replaces_file_with_unicode_and_leaves_no_tmp(
    tmp_path: Path, monkeypatch,
) -> None:
    path = tmp_path / "nested" / "manifest.json"
    path.parent.mkdir()
    path.write_text('{"old": true}\n', encoding="utf-8")

    original_write_text = Path.write_text
    encodings: list[str | None] = []

    def recording_write_text(self, data, *args, **kwargs):
        encodings.append(kwargs.get("encoding"))
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", recording_write_text)

    atomic_write_json(path, {"message": "你好, 🌍", "schema": SCHEMA_VERSION})

    assert encodings == ["utf-8"]
    assert json.loads(path.read_bytes().decode("utf-8")) == {
        "message": "你好, 🌍",
        "schema": SCHEMA_VERSION,
    }
    assert list(path.parent.glob("*.tmp")) == []


def test_append_jsonl_writes_one_unicode_json_record_per_line(tmp_path: Path) -> None:
    path = tmp_path / "events" / "events.jsonl"

    append_jsonl(path, {"text": "第一条", "number": 1})
    append_jsonl(path, {"text": "第二条", "number": 2})

    assert path.read_text().splitlines() == [
        '{"text": "第一条", "number": 1}',
        '{"text": "第二条", "number": 2}',
    ]


def test_append_raw_preserves_bytes_and_sha256_matches_hashlib(
    tmp_path: Path,
) -> None:
    path = tmp_path / "raw" / "stdout.bin"
    data = b"{\xff\x00}\n"

    append_raw(path, data)
    append_raw(path, b"tail")

    expected = data + b"tail"
    assert path.read_bytes() == expected
    assert sha256_file(path) == hashlib.sha256(expected).hexdigest()
