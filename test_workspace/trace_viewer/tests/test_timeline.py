import json

from trace_viewer.presentation import json_text, present_record
from trace_viewer.timeline import page_records, read_jsonl, read_stderr, unified_timeline


def test_record_paging_never_splits_a_record(repo_root):
    attempt = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1"
    records = unified_timeline(attempt)
    first, next_page = page_records(records, page=1, per_page=2)
    assert len(first) == 2
    assert all("payload" in item for item in first)
    assert next_page == 2


def test_invalid_jsonl_line_is_visible_and_later_lines_continue(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text('{"type":"start"}\nnot-json\n{"type":"turn.end"}\n', encoding="utf-8")
    records = read_jsonl(path, "agent")
    assert any(item.get("parse_error") for item in records)
    assert records[-1]["payload"]["type"] == "turn.end"


def test_stderr_categories_keep_complete_lines(tmp_path):
    path = tmp_path / "stderr.log"
    path.write_text("plain\nWARN full warning\ntimeout happened\nERROR boom\n", encoding="utf-8")
    records = read_stderr(path)
    assert [record["category"] for record in records] == ["log", "warning", "timeout", "error"]
    assert records[1]["payload"] == "WARN full warning"


def test_stderr_parses_python_timestamp_inherits_it_and_strips_ansi(tmp_path):
    path = tmp_path / "stderr.log"
    path.write_text(
        "2026-08-21 20:08:46,377 [INFO] started\n\x1b[32mcolored continuation\x1b[0m\n",
        encoding="utf-8",
    )

    records = read_stderr(path)

    assert [record["timestamp"] for record in records] == [
        "2026-08-21 20:08:46,377",
        "2026-08-21 20:08:46,377",
    ]
    assert records[1]["payload"] == "colored continuation"


def test_unified_timeline_contains_all_sources(repo_root):
    attempt = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1"
    records = unified_timeline(attempt)
    assert {item["source"] for item in records} == {"acp", "agent", "process", "stderr", "files", "completeness"}
    timestamps = [item["timestamp"] for item in records if item["timestamp"]]
    assert timestamps == sorted(timestamps)


def test_file_and_completeness_records_have_derived_timestamps(repo_root):
    attempt = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1"

    records = unified_timeline(attempt)
    derived = [record for record in records if record["source"] in {"files", "completeness"}]

    assert derived
    assert all(record["timestamp"] for record in derived)


def test_acp_response_summary_keeps_identity_but_hides_bulky_metadata():
    record = {
        "source": "acp",
        "index": 1,
        "timestamp": "2026-08-21T10:00:00+00:00",
        "payload": {
            "direction": "received",
            "message": {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "sessionId": "sess-123",
                    "agentInfo": {"name": "Box-Agent", "version": "0.8.87"},
                    "_meta": {"skills": [{"description": "NOISY-SKILL-METADATA"}]},
                },
            },
        },
    }

    shown = present_record(record)
    summary = "\n".join(field["value"] for field in shown["view"]["fields"])

    assert "sess-123" in summary
    assert "Box-Agent" in summary
    assert "NOISY-SKILL-METADATA" not in summary
    assert "NOISY-SKILL-METADATA" in shown["view"]["raw"]


def test_json_display_decodes_literal_unicode_escape_sequences():
    shown = json_text({"content": r"\u7ed9\u6211\u751f\u6210", "emoji": r"\ud83d\ude00"})

    assert "给我生成" in shown
    assert "😀" in shown
    assert r"\u7ed9" not in shown
