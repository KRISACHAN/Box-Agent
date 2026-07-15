from __future__ import annotations

from pathlib import Path

import pytest

import box_agent.agent as agent_module
from box_agent.agent import Agent
from box_agent.events import DoneEvent, StopReason
from box_agent.loop_guards import CompletionGate
from box_agent.tools.skill_preload import ACTIVE_SKILLS_HEADING, strip_active_skills


class DummyLLM:
    pass


@pytest.mark.asyncio
async def test_agent_run_forwards_core_execution_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    async def fake_run_agent_loop(**kwargs):
        captured.update(kwargs)
        yield DoneEvent(stop_reason=StopReason.END_TURN, final_content="done")

    monkeypatch.setattr(agent_module, "run_agent_loop", fake_run_agent_loop)

    gate = CompletionGate(required_changed_artifact_globs=("output/**/*.md",))
    agent = Agent(
        llm_client=DummyLLM(),
        system_prompt="system",
        tools=[],
        workspace_dir=str(tmp_path),
    )

    result = await agent.run(
        force_plan_start=True,
        completion_gate=gate,
        artifact_detection_enabled=False,
    )

    assert result == "done"
    assert captured["force_plan_start"] is True
    assert captured["completion_gate"] is gate
    assert captured["artifact_detection_enabled"] is False
    assert captured["active_skill_activator"] == agent.activate_skill_instructions


def test_agent_preserves_deduplicated_active_skills_across_prompt_updates(
    tmp_path: Path,
) -> None:
    agent = Agent(
        llm_client=DummyLLM(),
        system_prompt="system",
        tools=[],
        workspace_dir=str(tmp_path),
    )

    agent.activate_skill_instructions("pptx", "# Skill: pptx\n\nOld instructions.")
    agent.activate_skill_instructions("pptx", "# Skill: pptx\n\nOld instructions.")

    assert agent.system_prompt.count(ACTIVE_SKILLS_HEADING) == 1
    assert agent.system_prompt.count("Old instructions.") == 1

    base_prompt = strip_active_skills(agent.system_prompt).replace("system", "updated", 1)
    agent.set_system_prompt(base_prompt)
    agent.activate_skill_instructions("pptx", "# Skill: pptx\n\nNew instructions.")

    assert agent.messages[0].content == agent.system_prompt
    assert agent.system_prompt.startswith("updated")
    assert "Old instructions." not in agent.system_prompt
    assert agent.system_prompt.endswith("New instructions.")


def test_agent_reports_active_skill_budget_without_truncating_and_can_clear(
    tmp_path: Path,
) -> None:
    agent = Agent(
        llm_client=DummyLLM(),
        system_prompt="system",
        tools=[],
        workspace_dir=str(tmp_path),
    )
    first = "FIRST_REQUIRED_RULE\n" + "a" * 70_000
    second = "SECOND_REQUIRED_RULE\n" + "b" * 70_000

    agent.activate_skill_instructions("first", first)
    agent.activate_skill_instructions("second", second)
    diagnostics = agent.active_skill_diagnostics()

    assert diagnostics["names"] == ("first", "second")
    assert diagnostics["budget_exceeded"] is True
    assert "FIRST_REQUIRED_RULE" in agent.system_prompt
    assert "SECOND_REQUIRED_RULE" in agent.system_prompt

    assert agent.deactivate_skill_instructions("first") is True
    assert "FIRST_REQUIRED_RULE" not in agent.system_prompt
    assert "SECOND_REQUIRED_RULE" in agent.system_prompt
    assert agent.deactivate_skill_instructions("missing") is False

    agent.clear_active_skill_instructions()
    assert ACTIVE_SKILLS_HEADING not in agent.system_prompt
    assert agent.active_skill_diagnostics()["names"] == ()
