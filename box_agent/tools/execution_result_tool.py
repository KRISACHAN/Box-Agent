"""Host-neutral machine-readable execution result reporting."""

from __future__ import annotations

from typing import Any

from .base import Tool, ToolResult

_OUTCOMES = ("completed", "blocked", "needs_input")
_CHANGE_KINDS = ("code", "document", "design", "configuration", "other")
_CHECK_STATUSES = ("passed", "failed", "skipped")


def _text_list(values: list[Any] | None) -> list[str]:
    return [text for value in values or [] if (text := str(value).strip())]


class ReportExecutionResultTool(Tool):
    """Publish the execution facts that a host can bind to its own workflow."""

    @property
    def name(self) -> str:
        return "report_execution_result"

    @property
    def description(self) -> str:
        return (
            "Report the final, machine-readable result of the current execution to the "
            "host after the work and verification are finished. Report only observed "
            "changes, checks, limitations, and questions. A completed result requires "
            "at least one change; needs_input requires at least one question. This result "
            "does not submit, accept, or authorize work in any external team system: the "
            "host owns workflow identity, task versions, context, and submission."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": list(_OUTCOMES),
                    "description": "Execution outcome; never use completed to mean accepted.",
                },
                "summary": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                    "description": "Concise factual summary of the execution result.",
                },
                "changes": {
                    "type": "array",
                    "maxItems": 200,
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": list(_CHANGE_KINDS),
                            },
                            "summary": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1000,
                            },
                            "reference": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 2000,
                                "description": (
                                    "Host-resolvable file, artifact, URL, or other reference."
                                ),
                            },
                        },
                        "required": ["kind", "summary", "reference"],
                        "additionalProperties": False,
                    },
                },
                "checks": {
                    "type": "array",
                    "maxItems": 200,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 240,
                            },
                            "status": {
                                "type": "string",
                                "enum": list(_CHECK_STATUSES),
                            },
                            "summary": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 1000,
                            },
                            "reference": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 2000,
                            },
                        },
                        "required": ["name", "status", "summary"],
                        "additionalProperties": False,
                    },
                },
                "known_limitations": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
                "questions": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {"type": "string", "minLength": 1, "maxLength": 1000},
                },
            },
            "required": [
                "outcome",
                "summary",
                "changes",
                "checks",
                "known_limitations",
                "questions",
            ],
            "additionalProperties": False,
        }

    async def execute(
        self,
        outcome: str,
        summary: str,
        changes: list[dict[str, Any]] | None = None,
        checks: list[dict[str, Any]] | None = None,
        known_limitations: list[Any] | None = None,
        questions: list[Any] | None = None,
    ) -> ToolResult:
        normalized_outcome = outcome.strip().lower()
        normalized_summary = summary.strip()
        normalized_changes = [dict(item) for item in changes or []]
        normalized_checks = [dict(item) for item in checks or []]
        normalized_limitations = _text_list(known_limitations)
        normalized_questions = _text_list(questions)

        if normalized_outcome not in _OUTCOMES:
            return ToolResult(
                success=False,
                error=f"Unknown execution outcome: {outcome}",
            )
        if not normalized_summary:
            return ToolResult(
                success=False,
                error="Execution result summary is required.",
            )
        if normalized_outcome == "completed" and not normalized_changes:
            return ToolResult(
                success=False,
                error="Completed execution results require at least one change.",
            )
        if normalized_outcome == "needs_input" and not normalized_questions:
            return ToolResult(
                success=False,
                error="needs_input execution results require at least one question.",
            )

        raw_output = {
            "type": "execution_result",
            "version": 1,
            "outcome": normalized_outcome,
            "summary": normalized_summary,
            "changes": normalized_changes,
            "checks": normalized_checks,
            "knownLimitations": normalized_limitations,
            "questions": normalized_questions,
        }
        return ToolResult(
            success=True,
            content=f"Reported execution result: {normalized_outcome}.",
            raw_output=raw_output,
            model_context=(
                "The host received the machine-readable execution result. "
                "Do not claim that an external team workflow accepted it."
            ),
        )
