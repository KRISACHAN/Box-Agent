import json

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


def test_unified_timeline_contains_all_sources(repo_root):
    attempt = repo_root / "test_workspace/outputs/eval-one/cases/Q1/attempts/attempt-q1"
    records = unified_timeline(attempt)
    assert {item["source"] for item in records} == {"acp", "agent", "process", "stderr", "files", "completeness"}
    timestamps = [item["timestamp"] for item in records if item["timestamp"]]
    assert timestamps == sorted(timestamps)
