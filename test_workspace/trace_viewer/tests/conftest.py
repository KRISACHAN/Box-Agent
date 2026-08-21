import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trace_viewer.app import create_app


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def write_jsonl(path: Path, values: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values),
        encoding="utf-8",
    )


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    output = tmp_path / "test_workspace" / "outputs" / "eval-one"
    write_json(
        output / "manifest.json",
        {
            "schema_version": "box-agent-acp-eval/v1",
            "run_id": "run-test",
            "status": "completed_with_failures",
            "finished_at": "2026-08-21T10:00:00+00:00",
        },
    )
    write_json(
        output / "summary.json",
        {
            "schema_version": "box-agent-acp-eval/v1",
            "finished_at": "2026-08-21T10:00:00+00:00",
            "cases": [{"case_id": "Q1"}, {"case_id": "Q2"}],
        },
    )
    for case_id, status in (("Q1", "complete"), ("Q2", "incomplete")):
        case = output / "cases" / case_id
        attempt_id = f"attempt-{case_id.lower()}"
        attempt = case / "attempts" / attempt_id
        write_json(case / "input.json", {"id": case_id, "query": f"question {case_id}"})
        write_json(case / "latest.json", {"attempt_id": attempt_id, "path": f"attempts/{attempt_id}"})
        write_json(
            attempt / "run.json",
            {
                "schema_version": "box-agent-acp-eval/v1",
                "case_id": case_id,
                "attempt_id": attempt_id,
                "acp_status": "completed" if case_id == "Q1" else "error",
                "completeness_status": status,
                "process_exit_code": -15,
                "started_at": "2026-08-21T09:59:58+00:00",
                "finished_at": "2026-08-21T10:00:00+00:00",
                "stderr_counts": {"error": 1 if case_id == "Q2" else 0, "timeout": 0, "warning": 1},
            },
        )
        write_json(attempt / "completeness.json", {"status": status, "issues": [] if status == "complete" else ["missing"]})
        (attempt / "assistant.txt").write_text(f"answer {case_id}", encoding="utf-8")
        (attempt / "stderr.log").write_text("warning: demo\nerror: demo\n", encoding="utf-8")
        write_jsonl(attempt / "protocol.jsonl", [{"sequence": 1, "direction": "sent", "timestamp": "2026-08-21T09:59:58+00:00", "message": {"method": "initialize"}}])
        write_jsonl(attempt / "agent" / "trace.jsonl", [{"type": "turn.start", "timestamp": "2026-08-21T09:59:59+00:00"}])
        write_jsonl(attempt / "process.jsonl", [{"event": "process.started", "timestamp": "2026-08-21T09:59:58.5+00:00"}])
        write_json(attempt / "files-before.json", {"files": []})
        write_json(attempt / "files-after.json", {"files": []})
        write_json(attempt / "artifacts.json", {"artifacts": []})
    return tmp_path


@pytest.fixture
def client(repo_root: Path) -> TestClient:
    return TestClient(create_app(repo_root))
