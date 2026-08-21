from pathlib import Path

import pytest

from acp_eval import SCHEMA_VERSION
from acp_eval.models import AttemptManifest, RunResult
from acp_eval.stderr_scan import scan_stderr, summarize_stderr


@pytest.mark.parametrize(
    ("line", "category"),
    [
        ("[ERROR] failed to initialize", "error"),
        ("[WARNING] retrying", "warning"),
        ("[WARN] retrying", "warning"),
        ("level=warning: retrying", "warning"),
        ("An ERROR occurred", "error"),
        ("request TIMED OUT", "timeout"),
        ("request timeout", "timeout"),
        ("everything ERROR timed out WARNING", "error"),
    ],
)
def test_scan_stderr_classifies_lines_by_priority(
    tmp_path: Path, line: str, category: str
) -> None:
    path = tmp_path / "stderr.log"
    path.write_text(f"prefix\n{line}\nsuffix\n", encoding="utf-8")

    findings = scan_stderr(path)

    assert len(findings) == 1
    assert findings[0].category == category
    assert findings[0].line_number == 2
    assert findings[0].text == line


def test_scan_stderr_strips_ansi_only_for_matching_and_extracts_timestamp(
    tmp_path: Path,
) -> None:
    line = "\x1b[31m2026-08-21T00:12:34.125Z [ERROR] bad input\x1b[0m"
    path = tmp_path / "stderr.log"
    path.write_text(line + "\n", encoding="utf-8")

    findings = scan_stderr(path)

    assert findings[0].category == "error"
    assert findings[0].timestamp == "2026-08-21T00:12:34.125Z"
    assert findings[0].text == line


def test_scan_stderr_uses_word_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "stderr.log"
    path.write_text("errorCode warningness timeout_ms\n", encoding="utf-8")

    assert scan_stderr(path) == []


@pytest.mark.parametrize("title", ["ERROR hidden title", "WARNING hidden title"])
def test_scan_stderr_ignores_osc_title_words(tmp_path: Path, title: str) -> None:
    path = tmp_path / "stderr.log"
    path.write_text(f"\x1b]0;{title}\x07normal output\n", encoding="utf-8")

    assert scan_stderr(path) == []


def test_scan_stderr_preserves_osc_and_csi_sequences_in_finding_text(
    tmp_path: Path,
) -> None:
    line = "\x1b]0;window title\x1b\\\x1b[33m[WARN] visible warning\x1b[0m"
    path = tmp_path / "stderr.log"
    path.write_text(line + "\n", encoding="utf-8")

    findings = scan_stderr(path)

    assert findings[0].category == "warning"
    assert findings[0].text == line


@pytest.mark.parametrize("model", [AttemptManifest, RunResult])
def test_manifest_schema_version_is_not_constructor_supplied(model) -> None:
    with pytest.raises(TypeError, match="schema_version"):
        model(run_id="run-1", case_id="case-1", attempt_id="attempt-1", schema_version="other")

    instance = model(run_id="run-1", case_id="case-1", attempt_id="attempt-1")
    assert instance.to_dict()["schema_version"] == SCHEMA_VERSION


def test_summarize_stderr_returns_all_categories_in_stable_shape(
    tmp_path: Path,
) -> None:
    path = tmp_path / "stderr.log"
    path.write_text("error\nwarn\ntimeout\n", encoding="utf-8")

    assert summarize_stderr(scan_stderr(path)) == {
        "error": 1,
        "timeout": 1,
        "warning": 1,
    }


def test_attempt_manifest_serializes_v1_identity_and_lifecycle() -> None:
    manifest = AttemptManifest(
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        started_at="2026-08-21T00:12:34Z",
        finished_at="2026-08-21T00:12:35Z",
        status="complete",
    )

    assert manifest.to_dict() == {
        "schema_version": SCHEMA_VERSION,
        "run_id": "run-1",
        "case_id": "case-1",
        "attempt_id": "attempt-1",
        "started_at": "2026-08-21T00:12:34Z",
        "finished_at": "2026-08-21T00:12:35Z",
        "status": "complete",
    }


def test_run_result_serializes_status_exit_counts_and_completeness() -> None:
    result = RunResult(
        run_id="run-1",
        case_id="case-1",
        attempt_id="attempt-1",
        started_at="2026-08-21T00:12:34Z",
        finished_at="2026-08-21T00:12:35Z",
        acp_status="completed",
        process_exit_code=0,
        stderr_counts={"error": 1, "timeout": 0, "warning": 2},
        completeness_status="complete",
    )

    assert result.to_dict() == {
        "schema_version": SCHEMA_VERSION,
        "run_id": "run-1",
        "case_id": "case-1",
        "attempt_id": "attempt-1",
        "started_at": "2026-08-21T00:12:34Z",
        "finished_at": "2026-08-21T00:12:35Z",
        "acp_status": "completed",
        "process_exit_code": 0,
        "stderr_counts": {"error": 1, "timeout": 0, "warning": 2},
        "completeness_status": "complete",
    }
