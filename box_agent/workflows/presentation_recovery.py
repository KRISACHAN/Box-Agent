"""Durable recovery for an interrupted controlled-presentation workflow."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..loop_guards import CompletionGate
from .presentation_checkpoint import (
    CONTROLLED_PRESENTATION_CHECKPOINT_MARKER,
    completion_gate_progress_text,
)
from .presentation_contract import RESEARCH_MODE_OPTION
from .presentation_routing import build_presentation_completion_gate


def recover_presentation_completion_gate(
    workspace_dir: str | Path,
) -> CompletionGate | None:
    """Recover an incomplete presentation gate from canonical artifacts."""
    workspace = Path(workspace_dir)
    output = workspace / "output"
    if not output.is_dir():
        return None

    research_root = output / "research"
    has_research = research_root.is_dir() and any(
        path.is_file() for path in research_root.rglob("*")
    )
    has_checkpoint = has_research or any(
        path.is_file()
        for filename in ("outline.json", "deck.json", "index.html")
        for path in output.rglob(filename)
    )
    if not has_checkpoint:
        return None

    gate = build_presentation_completion_gate("继续制作 PPT", workspace)
    if gate is None:
        return None
    gate = replace(
        gate,
        workflow_options={
            **gate.workflow_options,
            RESEARCH_MODE_OPTION: "deep" if has_research else "auto",
        },
    )
    checkpoint = completion_gate_progress_text(gate, str(workspace))
    if checkpoint and (
        f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}complete" in checkpoint
    ):
        return None
    return gate


__all__ = ["recover_presentation_completion_gate"]
