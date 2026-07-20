"""Regression coverage for research-synthesis handoff validation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "box_agent"
    / "skills"
    / "research-synthesis"
    / "scripts"
    / "validate_research_artifacts.py"
)
SKILL_ROOT = VALIDATOR.parents[1]


def _write_focused_research(research: Path, *, dimensions: int = 3) -> None:
    research.mkdir(parents=True)
    for index in range(1, dimensions + 1):
        (research / f"topic_dim{index:02d}.md").write_text(
            f"# Dimension {index}\n\nEvidence for dimension {index}.\n",
            encoding="utf-8",
        )
    (research / "topic_cross_verification.md").write_text(
        "# Cross Verification\n\n## High Confidence\n\nConfirmed.\n",
        encoding="utf-8",
    )
    (research / "topic_insight.md").write_text(
        "# Insight\n\nCross-dimension conclusion.\n",
        encoding="utf-8",
    )


def test_validator_writes_success_report_for_reduced_focused_route(
    tmp_path: Path,
) -> None:
    research = tmp_path / "research"
    _write_focused_research(research)
    report = research / "qa" / "topic_research_check.json"

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--research-dir",
            str(research),
            "--topic",
            "topic",
            "--route",
            "B",
            "--min-dimensions",
            "3",
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["validator"] == "research-synthesis"
    assert payload["route"] == "B"
    assert payload["min_dimensions"] == 3
    assert payload["dimension_count"] == 3
    assert len(payload["files_checked"]) == 5


def test_validator_writes_failed_report_when_research_is_too_shallow(
    tmp_path: Path,
) -> None:
    research = tmp_path / "research"
    _write_focused_research(research, dimensions=2)
    report = research / "qa" / "topic_research_check.json"

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--research-dir",
            str(research),
            "--topic",
            "topic",
            "--route",
            "B",
            "--min-dimensions",
            "3",
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["dimension_count"] == 2
    assert "expected at least 3 dimension files, found 2" in payload["issues"]


def test_research_instructions_preserve_depth_without_rephrased_query_loops() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    routes = (SKILL_ROOT / "references" / "routes.md").read_text(encoding="utf-8")

    assert "covering distinct evidence gaps" in skill
    assert "do not rerun a near-equivalent" in skill
    assert "standalone Playwright MCP tools are separate" in skill
    assert "source_preference: playwright" in skill
    assert "five distinct evidence intents" in routes
    assert "reworded versions of an already-run entity/fact query do not add depth" in routes


def test_research_instructions_use_artifact_relative_validator_paths() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert '--research-dir "research"' in skill
    assert '--report "research/qa/{topic}_research_check.json"' in skill
    assert "do not use `$(pwd)/output/research`" in skill
    assert '--research-dir "{workspace}/research"' not in skill
