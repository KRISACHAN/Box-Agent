import re
from pathlib import Path
from typing import Literal, Sequence

from acp_eval.models import StderrFinding


PRIORITY = ("error", "timeout", "warning")
PATTERNS = {
    "error": re.compile(r"\berror\b", re.I),
    "timeout": re.compile(r"\b(?:timeout|timed out)\b", re.I),
    "warning": re.compile(r"\b(?:warning|warn)\b", re.I),
}

# This covers OSC control strings (window titles and similar metadata), CSI
# sequences (the common colour/cursor form), and other short ESC-prefixed
# controls without changing the source line we retain.
ANSI_ESCAPE = re.compile(
    r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)"
    r"|\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])"
)
ISO_TIMESTAMP = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)(?=\s|$)"
)


def _matching_text(line: str) -> str:
    return ANSI_ESCAPE.sub("", line)


def _timestamp(line: str) -> str | None:
    match = ISO_TIMESTAMP.match(line)
    return match.group("timestamp") if match else None


def scan_stderr(path: Path) -> list[StderrFinding]:
    """Classify matching stderr lines while retaining their original text."""

    findings: list[StderrFinding] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        matching_line = _matching_text(line)
        category: Literal["error", "timeout", "warning"] | None = None
        for candidate in PRIORITY:
            if PATTERNS[candidate].search(matching_line):
                category = candidate  # type: ignore[assignment]
                break
        if category is not None:
            findings.append(
                StderrFinding(
                    category=category,
                    line_number=line_number,
                    timestamp=_timestamp(matching_line),
                    text=line,
                )
            )
    return findings


def summarize_stderr(findings: Sequence[StderrFinding]) -> dict[str, int]:
    counts = {category: 0 for category in PRIORITY}
    for finding in findings:
        counts[finding.category] += 1
    return counts
