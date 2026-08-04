"""Host-neutral workflow policies composed by the shared runtime."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..loop_guards import CompletionGate
from ..workflow_policy import WorkflowPolicy
from .controlled_presentation import ControlledPresentationPolicy
from .presentation_contract import RESEARCH_MODE_OPTION
from .presentation_preflight import (
    build_presentation_preflight_result,
    build_presentation_recommendation_prompt,
    load_presentation_preflight_config,
)


def create_workflow_policy(
    *,
    workflow_kind: str | None,
    workspace_dir: str | None,
    artifact_root_dir: str | Path | None,
    workflow_options: Mapping[str, Any] | None = None,
) -> WorkflowPolicy | None:
    """Create a per-run policy without exposing implementations to the kernel."""
    if workflow_kind == ControlledPresentationPolicy.kind:
        research_mode = (workflow_options or {}).get(RESEARCH_MODE_OPTION)
        return ControlledPresentationPolicy(
            workspace_dir=workspace_dir,
            artifact_root_dir=artifact_root_dir,
            research_mode=(
                research_mode if isinstance(research_mode, str) else None
            ),
        )
    return None


def recover_completion_gate(
    workspace_dir: str | Path,
) -> CompletionGate | None:
    """Recover the first incomplete built-in workflow from durable artifacts."""
    from .presentation_recovery import recover_presentation_completion_gate

    return recover_presentation_completion_gate(workspace_dir)


__all__ = [
    "ControlledPresentationPolicy",
    "build_presentation_preflight_result",
    "build_presentation_recommendation_prompt",
    "create_workflow_policy",
    "load_presentation_preflight_config",
    "recover_completion_gate",
]
