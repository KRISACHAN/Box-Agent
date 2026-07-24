"""Tests for workflow-policy composition outside the agent kernel."""

import inspect

from box_agent.core import run_agent_loop as core_run_agent_loop
from box_agent.loop_guards import CompletionGate
from box_agent.runtime import run_agent_loop
from box_agent.workflows import create_workflow_policy
from box_agent.workflows.controlled_presentation import ControlledPresentationPolicy
from box_agent.workflows.presentation_checkpoint import (
    CONTROLLED_PRESENTATION_CHECKPOINT_MARKER,
)


def test_runtime_bridge_preserves_kernel_signature() -> None:
    assert inspect.signature(run_agent_loop) == inspect.signature(core_run_agent_loop)


def test_factory_builds_controlled_presentation_policy(tmp_path) -> None:
    policy = create_workflow_policy(
        workflow_kind="controlled_presentation",
        workspace_dir=str(tmp_path),
        artifact_root_dir=tmp_path / "artifacts",
        workflow_options={"research_mode": "deep"},
    )

    assert isinstance(policy, ControlledPresentationPolicy)
    assert policy.research_mode == "deep"


def test_completion_gate_uses_generic_workflow_options_contract(tmp_path) -> None:
    gate = CompletionGate(
        workflow_checkpoint_kind="controlled_presentation",
        workflow_options={"research_mode": "deep"},
    )

    policy = create_workflow_policy(
        workflow_kind=gate.workflow_checkpoint_kind,
        workspace_dir=str(tmp_path),
        artifact_root_dir=None,
        workflow_options=gate.workflow_options,
    )

    assert "workflow_options" in inspect.signature(CompletionGate).parameters
    assert "presentation_research_mode" not in inspect.signature(
        CompletionGate
    ).parameters
    assert isinstance(policy, ControlledPresentationPolicy)
    assert policy.research_mode == "deep"


def test_factory_ignores_unknown_workflow(tmp_path) -> None:
    policy = create_workflow_policy(
        workflow_kind="third_party_workflow",
        workspace_dir=str(tmp_path),
        artifact_root_dir=None,
    )

    assert policy is None


def test_checkpoint_update_uses_generic_contract_fields(tmp_path) -> None:
    policy = ControlledPresentationPolicy(
        workspace_dir=str(tmp_path),
        artifact_root_dir=None,
    )

    first = policy.update_checkpoint(
        f"checkpoint\n{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}outline\n"
    )
    repeated = policy.update_checkpoint(first.text)

    assert first.changed is True
    assert first.recovered_evidence_urls == frozenset()
    assert repeated.changed is False
    assert policy.stage == "outline"
