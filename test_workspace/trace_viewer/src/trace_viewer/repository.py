"""Simple readers for box-agent-acp-eval/v1 output directories."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trace_viewer.timeline import source_records


SCHEMA_VERSION = "box-agent-acp-eval/v1"


class NotFoundError(LookupError):
    pass


class EvaluationRepository:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.outputs_root = self.repo_root / "test_workspace" / "outputs"

    @staticmethod
    def _json(path: Path, default: Any = None) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return default

    def _under(self, root: Path, *parts: str) -> Path:
        path = root.joinpath(*parts).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as error:
            raise NotFoundError("path is outside the evaluation output") from error
        return path

    def run_path(self, run_name: str) -> Path:
        path = self._under(self.outputs_root, run_name)
        if not path.is_dir() or path.parent != self.outputs_root.resolve():
            raise NotFoundError(run_name)
        return path

    def list_runs(self) -> list[dict[str, Any]]:
        if not self.outputs_root.is_dir():
            return []
        runs: list[dict[str, Any]] = []
        for path in sorted(self.outputs_root.iterdir(), key=lambda item: item.name):
            if path.name.startswith(".") or not path.is_dir():
                continue
            manifest = self._json(path / "manifest.json", {})
            if manifest.get("schema_version") != SCHEMA_VERSION:
                continue
            summary = self._json(path / "summary.json", {})
            cases = summary.get("cases") if isinstance(summary.get("cases"), list) else []
            if not cases:
                cases_dir = path / "cases"
                cases = list(cases_dir.iterdir()) if cases_dir.is_dir() else []
            runs.append(
                {
                    "name": path.name,
                    "task_count": len(cases),
                    "finished_at": summary.get("finished_at") or manifest.get("finished_at"),
                    "status": summary.get("status") or manifest.get("status"),
                }
            )
        return runs

    def _attempt_path(self, case_path: Path) -> Path:
        latest = self._json(case_path / "latest.json", {})
        attempt_id = latest.get("attempt_id")
        if isinstance(attempt_id, str):
            candidate = self._under(case_path / "attempts", attempt_id)
            if candidate.is_dir():
                return candidate
        attempts = case_path / "attempts"
        choices = sorted((path for path in attempts.iterdir() if path.is_dir()), reverse=True) if attempts.is_dir() else []
        if not choices:
            raise NotFoundError(case_path.name)
        return choices[0]

    @staticmethod
    def _duration(run: dict[str, Any]) -> float | None:
        try:
            start = datetime.fromisoformat(str(run["started_at"]).replace("Z", "+00:00"))
            finish = datetime.fromisoformat(str(run["finished_at"]).replace("Z", "+00:00"))
            return round((finish - start).total_seconds(), 3)
        except (KeyError, TypeError, ValueError):
            return None

    def _case_summary(self, case_path: Path) -> dict[str, Any]:
        input_data = self._json(case_path / "input.json", {})
        try:
            attempt = self._attempt_path(case_path)
        except NotFoundError:
            return {
                "case_id": case_path.name,
                "query": input_data.get("query"),
                "acp_status": "missing",
                "completeness_status": "incomplete",
                "duration": None,
                "stderr_counts": {"error": 0, "timeout": 0, "warning": 0},
            }
        run = self._json(attempt / "run.json", {})
        return {
            "case_id": case_path.name,
            "query": input_data.get("query"),
            "attempt_id": attempt.name,
            "attempt_path": attempt,
            "acp_status": run.get("acp_status") or "unknown",
            "completeness_status": run.get("completeness_status") or "incomplete",
            "duration": self._duration(run),
            "stderr_counts": run.get("stderr_counts") or {"error": 0, "timeout": 0, "warning": 0},
            "run": run,
        }

    def list_cases(self, run_name: str, query: str = "") -> list[dict[str, Any]]:
        cases_dir = self.run_path(run_name) / "cases"
        if not cases_dir.is_dir():
            return []
        needle = query.casefold().strip()
        cases = [self._case_summary(path) for path in sorted(cases_dir.iterdir()) if path.is_dir()]
        if needle:
            cases = [case for case in cases if needle in str(case["case_id"]).casefold() or needle in str(case.get("query") or "").casefold()]
        return cases

    def get_case(self, run_name: str, case_id: str) -> dict[str, Any]:
        case_path = self._under(self.run_path(run_name) / "cases", case_id)
        if not case_path.is_dir():
            raise NotFoundError(case_id)
        result = self._case_summary(case_path)
        if "attempt_path" not in result:
            raise NotFoundError(case_id)
        attempt = result["attempt_path"]
        result.update(
            {
                "input": self._json(case_path / "input.json", {}),
                "assistant": self._final_answer(attempt),
                "completeness": self._json(attempt / "completeness.json", {}),
                "case_path": case_path,
            }
        )
        return result

    def _final_answer(self, attempt: Path) -> str:
        latest = ""
        for record in source_records(attempt, "agent"):
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("event") != "turn.output" and payload.get("type") != "turn.output":
                continue
            data = payload.get("data")
            if not isinstance(data, dict):
                continue
            content = data.get("content") or data.get("output")
            if isinstance(content, str) and content:
                latest = content
        return latest or self._text(attempt / "assistant.txt")

    def diagnosis_path(self, run_name: str, case_id: str) -> Path | None:
        case_path = self.get_case(run_name, case_id)["case_path"]
        path = case_path / "diagnosis.md"
        return path if path.is_file() else None

    def diagnosis_text(self, run_name: str, case_id: str) -> str | None:
        path = self.diagnosis_path(run_name, case_id)
        return self._text(path) if path else None

    @staticmethod
    def _text(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def resolve_case_path(self, run_name: str, case_id: str, relative: str) -> Path:
        attempt = self.get_case(run_name, case_id)["attempt_path"]
        path = self._under(attempt, relative)
        if not path.is_file():
            raise NotFoundError(relative)
        return path
