from __future__ import annotations

import asyncio
from dataclasses import dataclass, fields
from types import SimpleNamespace

from box_agent.acp import SessionState
from box_agent.agent_run import AgentRunHandle


def _compatibility_state() -> SimpleNamespace:
    return SimpleNamespace(
        agent=SimpleNamespace(goal=object()),
        cancelled=False,
        inject_queue=asyncio.Queue(),
        turn_active=False,
        current_turn_id="turn-1",
        explicitly_allowed_skill_names={"skill-a"},
        skill_selector=object(),
        skill_runtime_context=object(),
        preloaded_skill_names=["skill-a"],
        preloaded_skill_hashes={"skill-a": "hash-a"},
        preloaded_skill_attributions={"skill-a": object()},
    )


def test_agent_run_handle_proxies_mutable_run_and_skill_state() -> None:
    state = _compatibility_state()
    handle = AgentRunHandle(state)

    assert handle.state is state
    assert handle.agent is state.agent
    assert handle.goal is state.agent.goal
    assert handle.inject_queue is state.inject_queue
    assert handle.explicitly_allowed_skill_names is state.explicitly_allowed_skill_names
    assert handle.skill_selector is state.skill_selector
    assert handle.skill_runtime_context is state.skill_runtime_context
    assert handle.preloaded_skill_names is state.preloaded_skill_names
    assert handle.preloaded_skill_hashes is state.preloaded_skill_hashes
    assert handle.preloaded_skill_attributions is state.preloaded_skill_attributions

    handle.cancelled = True
    handle.turn_active = True
    handle.current_turn_id = "turn-2"

    assert state.cancelled is True
    assert state.turn_active is True
    assert state.current_turn_id == "turn-2"


def test_agent_run_handle_builds_options_from_agent_defaults() -> None:
    @dataclass(frozen=True)
    class Options:
        default: str
        override: str = "original"

    state = SimpleNamespace(
        agent=SimpleNamespace(
            goal=None,
            default_run_options=lambda: Options(default="agent-default"),
        ),
    )

    options = AgentRunHandle(state).build_run_options(override="adapter-value")

    assert options == Options(default="agent-default", override="adapter-value")


def test_session_state_keeps_legacy_fields_and_exposes_same_run_handle() -> None:
    state = SessionState(agent=SimpleNamespace(goal=object()))

    assert isinstance(state.run_handle, AgentRunHandle)
    assert "run_handle" not in {item.name for item in fields(SessionState)}
    assert state.run_handle.state is state
    assert state.run_handle.inject_queue is state.inject_queue
    assert state.run_handle.explicitly_allowed_skill_names is (
        state.explicitly_allowed_skill_names
    )
    assert state.run_handle.preloaded_skill_names is state.preloaded_skill_names

    state.run_handle.cancelled = True
    assert state.cancelled is True
