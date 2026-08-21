from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from acp_eval import SCHEMA_VERSION


@dataclass(frozen=True)
class StderrFinding:
    category: Literal["error", "timeout", "warning"]
    line_number: int
    timestamp: str | None
    text: str


@dataclass
class AttemptManifest:
    """The identity and lifecycle metadata for one captured attempt."""

    run_id: str
    case_id: str
    attempt_id: str
    started_at: str | None = None
    finished_at: str | None = None
    status: str = "starting"
    schema_version: str = field(default=SCHEMA_VERSION, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "attempt_id": self.attempt_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
        }


@dataclass
class RunResult:
    """The observed ACP/process outcome and collection status for an attempt."""

    run_id: str
    case_id: str
    attempt_id: str
    started_at: str | None = None
    finished_at: str | None = None
    acp_status: str | None = None
    process_exit_code: int | None = None
    stderr_counts: Mapping[str, int] = field(
        default_factory=lambda: {"error": 0, "timeout": 0, "warning": 0}
    )
    completeness_status: str = "incomplete"
    schema_version: str = field(default=SCHEMA_VERSION, init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "attempt_id": self.attempt_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "acp_status": self.acp_status,
            "process_exit_code": self.process_exit_code,
            "stderr_counts": dict(self.stderr_counts),
            "completeness_status": self.completeness_status,
        }
