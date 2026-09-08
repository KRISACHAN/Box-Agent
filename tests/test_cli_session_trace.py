"""Native CLI tracing through the real Agent and LLM wrapper boundaries."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import box_agent.cli as cli
from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.llm.llm_wrapper import LLMClient
from box_agent.schema import FunctionCall, LLMResponse, StreamEvent, TokenUsage, ToolCall
from box_agent.session_trace import (
    SessionTraceWriter,
    emit_session_trace,
    reset_session_trace_writer,
    set_session_trace_writer,
)
from tests.test_session_trace import EchoTool


class ToolThenAnswerProvider:
    retry_callback = None

    def __init__(self):
        self.calls = 0

    async def generate_stream(self, messages, tools=None, **kwargs):
        self.calls += 1
        if self.calls % 2:
            yield StreamEvent(
                type="finish", finish_reason="tool_use",
                tool_calls=[ToolCall(
                    id=f"echo-{self.calls}", type="function",
                    function=FunctionCall(name="echo", arguments={"text": "ping"}),
                )],
                usage=TokenUsage(prompt_tokens=7, completion_tokens=2, total_tokens=9),
            )
        else:
            yield StreamEvent(type="text", delta="native trace answer")
            yield StreamEvent(
                type="finish", finish_reason="stop",
                usage=TokenUsage(prompt_tokens=10, completion_tokens=3, total_tokens=13),
            )

    async def generate(self, messages, tools=None, **kwargs):
        return LLMResponse(content='{"continue": false}', finish_reason="stop")


@pytest.fixture
def cli_trace_setup(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("BOX_AGENT_SESSION_TRACE_ENABLED", raising=False)
    trace_dir = tmp_path / "traces"
    monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_DIR", str(trace_dir))
    monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_RETENTION_ENABLED", "0")
    config_file = tmp_path / "config.yaml"
    config_file.write_text("offline: true\n", encoding="utf-8")
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Answer the user. {SANDBOX_INFO}", encoding="utf-8")
    workspace = tmp_path / "workspace"
    config = Config(
        llm=LLMConfig(api_key="test-only-key", retry={"enabled": False}),
        agent=AgentConfig(
            workspace_dir=str(workspace), max_steps=4,
            system_prompt_path=str(prompt_file), enable_memory=False,
            enable_memory_extraction=False, memory_maintainer_enabled=False,
            memory_promotion_proposal_enabled=False,
        ),
        tools=ToolsConfig(
            enable_mcp=False, enable_skills=False, enable_bash=False,
            enable_file_tools=False, enable_todo=False, enable_plan=False,
            enable_sub_agent=False, allow_full_access=True,
        ),
    )

    def client_factory(**kwargs):
        client = LLMClient(**kwargs)
        client._client = ToolThenAnswerProvider()
        return client

    async def base_tools(*args, **kwargs):
        return [EchoTool()], None, None, None

    monkeypatch.setattr(cli.Config, "get_default_config_path", staticmethod(lambda: config_file))
    monkeypatch.setattr(cli.Config, "from_yaml", staticmethod(lambda _: config))
    monkeypatch.setattr(cli, "LLMClient", client_factory)
    monkeypatch.setattr(cli, "initialize_base_tools", base_tools)
    monkeypatch.setattr(cli, "add_workspace_tools", lambda *args, **kwargs: None)
    return workspace, trace_dir


def read_records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def run_task(workspace, **kwargs):
    return await cli.run_agent(
        workspace, task="echo ping", sandbox_mode=False, verify_api=False,
        goal_autopilot_enabled=False, **kwargs,
    )


@pytest.mark.asyncio
async def test_cli_task_writes_native_lifecycle_llm_and_tool_records(cli_trace_setup):
    workspace, trace_dir = cli_trace_setup
    assert await run_task(workspace) == 0

    files = list(trace_dir.glob("*.jsonl"))
    assert len(files) == 1, "ordinary CLI runs must create their own trace"
    records = read_records(files[0])
    events = [record["event"] for record in records]
    assert events[0] == "session.start"
    assert events[1] == "turn.input"
    assert events[-2:] == ["turn.output", "turn.end"]
    assert {"llm.request", "llm.response", "tool.request", "tool.response"} <= set(events)
    assert records[0]["data"]["entrypoint"] == "cli"
    assert records[0]["data"]["workspace"] == str(workspace)
    assert records[1]["data"]["content"] == "echo ping"
    assert records[-2]["data"] == {"content": "native trace answer", "stop_reason": "end_turn"}
    assert records[-1]["data"]["stop_reason"] == "end_turn"
    assert records[-1]["data"]["duration_ms"] >= 0
    assert "usage" not in records[-1]["data"], "do not replace actual LLM usage with fake zero totals"
    assert len({record["session_id"] for record in records}) == 1
    assert all(record["acp_session_id"] == "" for record in records)
    assert len({record["turn_id"] for record in records[1:]}) == 1
    assert records[1]["turn_id"]


@pytest.mark.asyncio
async def test_cli_interactive_turns_share_file_but_not_turn_ids(cli_trace_setup, monkeypatch):
    workspace, trace_dir = cli_trace_setup
    inputs = iter(["/help", "first message", "/clear", "second message", "/exit"])

    class Prompts:
        def __init__(self, *args, **kwargs):
            pass

        async def prompt_async(self, *args, **kwargs):
            emit_session_trace("outside.turn")
            return next(inputs)

    monkeypatch.setattr(cli, "PromptSession", Prompts)
    assert await cli.run_agent(workspace, sandbox_mode=False, verify_api=False) == 0
    files = list(trace_dir.glob("*.jsonl"))
    assert len(files) == 1
    records = read_records(files[0])
    assert not any(record["event"] == "outside.turn" for record in records)
    turns = [record for record in records if record["event"] == "turn.input"]
    assert [record["data"]["content"] for record in turns] == ["first message", "second message"]
    assert len({record["turn_id"] for record in turns}) == 2
    assert len([record for record in records if record["event"] == "turn.end"]) == 2
    assert all(record["turn_id"] in {turn["turn_id"] for turn in turns} for record in records[1:])


@pytest.mark.asyncio
async def test_cli_trace_restores_outer_context_and_separates_invocations(cli_trace_setup):
    workspace, trace_dir = cli_trace_setup
    outer = SessionTraceWriter(session_id="outer", acp_session_id="", trace_dir=trace_dir / "outer")
    token = set_session_trace_writer(outer, turn_id="outer-turn")
    try:
        assert await run_task(workspace) == 0
        emit_session_trace("outer.after")
        assert await run_task(workspace) == 0
    finally:
        reset_session_trace_writer(token)
    assert [record["event"] for record in read_records(outer.file_path)] == ["outer.after"]
    assert len(list(trace_dir.glob("*.jsonl"))) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["disabled", "unwritable"])
async def test_cli_trace_optout_or_write_failure_does_not_change_task(cli_trace_setup, monkeypatch, mode):
    workspace, trace_dir = cli_trace_setup
    if mode == "disabled":
        monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_ENABLED", "0")
    else:
        trace_dir.write_text("not a directory", encoding="utf-8")
    assert await run_task(workspace) == 0
    assert not list(trace_dir.glob("*.jsonl"))


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", ["0", "1"])
async def test_cli_trace_path_resolution_failure_does_not_change_task(cli_trace_setup, monkeypatch, enabled):
    workspace, trace_dir = cli_trace_setup
    monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_ENABLED", enabled)
    monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_DIR", "~definitely-missing-trace-user/traces")
    assert await run_task(workspace) == 0
    assert not list(trace_dir.glob("*.jsonl"))


@pytest.mark.asyncio
async def test_cli_interactive_cancellation_settles_run_before_ending_trace(cli_trace_setup, monkeypatch):
    workspace, trace_dir = cli_trace_setup
    inputs = iter(["cancel this turn", "/exit"])
    owner = asyncio.current_task()
    children = []

    class Prompts:
        def __init__(self, *args, **kwargs):
            pass

        async def prompt_async(self, *args, **kwargs):
            return next(inputs)

    async def cancelled_run(agent, *args, **kwargs):
        children.append(asyncio.current_task())
        emit_session_trace("test.child_started")
        owner.cancel()
        try:
            await asyncio.sleep(0.05)
        finally:
            emit_session_trace("test.child_settled")
        return "should not finish normally"

    monkeypatch.setattr(cli, "PromptSession", Prompts)
    monkeypatch.setattr(cli.Agent, "run", cancelled_run)
    try:
        assert await cli.run_agent(workspace, sandbox_mode=False, verify_api=False) == 0
    finally:
        await asyncio.gather(*children, return_exceptions=True)
    records = read_records(next(trace_dir.glob("*.jsonl")))
    events = [record["event"] for record in records]
    assert events.index("test.child_settled") < events.index("turn.end")
    assert children[0].cancelled()
    assert records[-1]["data"]["stop_reason"] == "cancelled"
    assert "turn.error" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["error", "waiting_for_user", "max_steps", "max_tokens", "cancelled"])
async def test_cli_trace_preserves_internal_stop_reason(cli_trace_setup, monkeypatch, reason):
    workspace, trace_dir = cli_trace_setup

    async def stopped_run(agent, *args, **kwargs):
        agent.last_stop_reason = reason
        return "observed result"

    monkeypatch.setattr(cli.Agent, "run", stopped_run)
    assert await run_task(workspace) == (1 if reason == "error" else 0)
    records = read_records(next(trace_dir.glob("*.jsonl")))
    assert records[-1]["data"]["stop_reason"] == reason
    assert records[-2]["data"] == {"content": "observed result", "stop_reason": reason}
    errors = [record for record in records if record["event"] == "turn.error"]
    assert len(errors) == (1 if reason == "error" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_type", [RuntimeError, asyncio.CancelledError, KeyboardInterrupt])
async def test_cli_trace_closes_failed_turn_and_restores_context(cli_trace_setup, monkeypatch, failure_type):
    workspace, trace_dir = cli_trace_setup

    async def fail_run(agent, *args, **kwargs):
        emit_session_trace("test.inside")
        raise failure_type("trace failure probe")

    monkeypatch.setattr(cli.Agent, "run", fail_run)
    if failure_type is RuntimeError:
        assert await run_task(workspace) == 1
    else:
        with pytest.raises(failure_type, match="trace failure probe"):
            await run_task(workspace)
    emit_session_trace("test.outside")
    records = read_records(next(trace_dir.glob("*.jsonl")))
    assert any(record["event"] == "test.inside" for record in records)
    assert not any(record["event"] == "test.outside" for record in records)
    assert records[-1]["event"] == "turn.end"
    expected = "error" if failure_type is RuntimeError else "cancelled"
    assert records[-1]["data"]["stop_reason"] == expected
    errors = [record for record in records if record["event"] == "turn.error"]
    assert len(errors) == (1 if failure_type is RuntimeError else 0)
    if errors:
        assert errors[0]["data"]["error_type"] == "RuntimeError"
        assert errors[0]["data"]["message"] == "trace failure probe"


@pytest.mark.asyncio
async def test_cli_goal_continuations_keep_one_input_and_only_final_output(cli_trace_setup, monkeypatch):
    workspace, trace_dir = cli_trace_setup
    answers = iter(["intermediate plan", "completed goal"])

    async def goal_run(agent, *args, **kwargs):
        answer = next(answers)
        emit_session_trace("test.goal_step", data={"answer": answer})
        agent.last_stop_reason = "end_turn"
        if answer == "completed goal":
            agent.goal.status = "complete"
        return answer

    monkeypatch.setattr(cli.Agent, "run", goal_run)
    assert await cli.run_agent(
        workspace, task="finish the goal", initial_goal="finish the goal",
        sandbox_mode=False, verify_api=False, goal_autopilot_enabled=True,
    ) == 0
    records = read_records(next(trace_dir.glob("*.jsonl")))
    assert len([record for record in records if record["event"] == "turn.input"]) == 1
    steps = [record for record in records if record["event"] == "test.goal_step"]
    assert [record["data"]["answer"] for record in steps] == ["intermediate plan", "completed goal"]
    outputs = [record for record in records if record["event"] == "turn.output"]
    assert len(outputs) == 1
    assert outputs[0]["data"]["content"] == "completed goal"
    assert len({record["turn_id"] for record in records[1:]}) == 1
