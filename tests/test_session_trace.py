"""Tests for best-effort per-session JSONL execution traces."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from box_agent.acp import BoxACPAgent
from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.core import run_agent_loop
from box_agent.llm.llm_wrapper import LLMClient
from box_agent.schema import (
    FunctionCall,
    LLMProvider,
    Message,
    StreamEvent,
    TokenUsage,
    ToolCall,
)
from box_agent.session_trace import (
    SessionTraceWriter,
    emit_session_trace,
    reset_session_trace_writer,
    safe_session_trace_name,
    scoped_session_trace,
    set_session_trace_writer,
)
from box_agent.tools.base import Tool, ToolResult


def _records(writer: SessionTraceWriter) -> list[dict]:
    return [json.loads(line) for line in writer.file_path.read_text(encoding="utf-8").splitlines()]


class EchoTool(Tool):
    @property
    def name(self):
        return "echo"

    @property
    def description(self):
        return "Echo text"

    @property
    def parameters(self):
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str = ""):
        return ToolResult(success=True, content=f"echo:{text}")


def test_writer_appends_jsonl_and_preserves_ids_with_redaction(tmp_path):
    writer = SessionTraceWriter(
        session_id="office/session 1",
        acp_session_id="sess-0-abcd1234",
        trace_dir=tmp_path,
        enabled=True,
    )

    writer.write(
        "turn.input",
        turn_id="turn-1",
        data={"content": "hello", "authorization": "Bearer secret", "total_tokens": 12},
    )
    writer.write("turn.output", turn_id="turn-1", data={"content": "world"})
    same_session_writer = SessionTraceWriter(
        session_id="office/session 1",
        acp_session_id="sess-1-efgh5678",
        trace_dir=tmp_path,
        enabled=True,
    )
    same_session_writer.write("session.start")

    assert writer.file_path.name == safe_session_trace_name("office/session 1")
    assert same_session_writer.file_path == writer.file_path
    records = _records(writer)
    assert [record["event"] for record in records] == [
        "turn.input",
        "turn.output",
        "session.start",
    ]
    assert all(record["session_id"] == "office/session 1" for record in records)
    assert records[:2][0]["acp_session_id"] == "sess-0-abcd1234"
    assert records[:2][1]["acp_session_id"] == "sess-0-abcd1234"
    assert records[2]["acp_session_id"] == "sess-1-efgh5678"
    assert all(record["turn_id"] == "turn-1" for record in records[:2])
    assert records[0]["data"]["authorization"] == "<redacted>"
    assert records[0]["data"]["total_tokens"] == 12


def test_writer_failure_never_escapes_into_agent_flow(tmp_path):
    blocked_trace_dir = tmp_path / "not-a-directory"
    blocked_trace_dir.write_text("occupied", encoding="utf-8")
    writer = SessionTraceWriter(
        session_id="office-session-failure",
        acp_session_id="sess-failure",
        trace_dir=blocked_trace_dir,
        enabled=True,
    )

    writer.write("turn.input", turn_id="turn-failure", data={"content": "still safe"})

    assert blocked_trace_dir.read_text(encoding="utf-8") == "occupied"


@pytest.mark.asyncio
async def test_scoped_trace_can_be_closed_from_another_task_context(tmp_path):
    writer = SessionTraceWriter(
        session_id="office-session-close",
        acp_session_id="sess-close",
        trace_dir=tmp_path,
        enabled=True,
    )

    async def source():
        try:
            emit_session_trace("source.next")
            yield "event"
        finally:
            emit_session_trace("source.close")

    stream = scoped_session_trace(source(), writer=writer, turn_id="turn-close")
    assert await anext(stream) == "event"
    await asyncio.create_task(stream.aclose())

    assert [record["event"] for record in _records(writer)] == [
        "source.next",
        "source.close",
    ]


@pytest.mark.asyncio
async def test_llm_wrapper_records_request_response_tokens_and_ttfb(tmp_path):
    class FakeUnderlying:
        retry_callback = None

        async def generate_stream(self, messages, tools=None, **kwargs):
            yield StreamEvent(type="text", delta="hello")
            yield StreamEvent(
                type="finish",
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=7, completion_tokens=2, total_tokens=9),
                provider_response_id="chatcmpl-provider-response-1",
                provider_request_id="provider-request-1",
            )

    client = LLMClient(api_key="test", provider=LLMProvider.ANTHROPIC, model="test-model")
    client._client = FakeUnderlying()
    writer = SessionTraceWriter(
        session_id="office-session-1",
        acp_session_id="sess-1",
        trace_dir=tmp_path,
        enabled=True,
    )
    token = set_session_trace_writer(writer, turn_id="turn-1")
    try:
        events = [
            event
            async for event in client.generate_stream(
                [Message(role="user", content="full input")],
                [EchoTool()],
                session_id="office-session-1",
                turn_id="turn-1",
            )
        ]
    finally:
        reset_session_trace_writer(token)

    assert [event.type for event in events] == ["text", "finish"]
    records = _records(writer)
    request, response = records
    assert request["event"] == "llm.request"
    assert request["data"]["messages"][0]["content"] == "full input"
    assert request["data"]["tools"][0]["name"] == "echo"
    assert response["event"] == "llm.response"
    assert response["llm_call_id"] == request["llm_call_id"]
    assert response["data"]["content"] == "hello"
    assert response["data"]["provider_response_id"] == "chatcmpl-provider-response-1"
    assert response["data"]["provider_request_id"] == "provider-request-1"
    assert response["data"]["usage"] == {
        "prompt_tokens": 7,
        "completion_tokens": 2,
        "total_tokens": 9,
    }
    assert isinstance(response["data"]["timing"]["ttfb_ms"], int)
    assert response["data"]["timing"]["ttfb_ms"] <= response["data"]["timing"]["duration_ms"]


@pytest.mark.asyncio
async def test_core_records_tool_request_and_response_without_changing_events(tmp_path):
    class ToolThenDoneLLM:
        def __init__(self):
            self.calls = 0

        async def generate_stream(self, messages, tools=None, **kwargs):
            self.calls += 1
            if self.calls == 1:
                yield StreamEvent(
                    type="finish",
                    finish_reason="tool",
                    tool_calls=[
                        ToolCall(
                            id="tool-1",
                            type="function",
                            function=FunctionCall(name="echo", arguments={"text": "ping"}),
                        )
                    ],
                )
            else:
                yield StreamEvent(type="text", delta="done")
                yield StreamEvent(type="finish", finish_reason="stop")

    writer = SessionTraceWriter(
        session_id="office-session-2",
        acp_session_id="sess-2",
        trace_dir=tmp_path,
        enabled=True,
    )
    messages = [Message(role="system", content="sys"), Message(role="user", content="go")]
    original_events = run_agent_loop(
        llm=ToolThenDoneLLM(),
        messages=messages,
        tools={"echo": EchoTool()},
        max_steps=3,
        session_id="office-session-2",
        turn_id="turn-2",
    )
    events = [
        event
        async for event in scoped_session_trace(
            original_events,
            writer=writer,
            turn_id="turn-2",
        )
    ]

    records = _records(writer)
    request = next(record for record in records if record["event"] == "tool.request")
    response = next(record for record in records if record["event"] == "tool.response")
    assert request["tool_call_id"] == "tool-1"
    assert request["data"]["arguments"] == {"text": "ping"}
    assert response["tool_call_id"] == "tool-1"
    assert response["data"]["success"] is True
    assert response["data"]["content"] == "echo:ping"
    assert any(type(event).__name__ == "ToolCallStart" for event in events)
    assert any(type(event).__name__ == "ToolCallResult" for event in events)


@pytest.mark.asyncio
async def test_acp_uses_upstream_session_id_without_changing_generated_acp_id(tmp_path, monkeypatch):
    class DummyConn:
        async def sessionUpdate(self, payload):
            return None

    class DoneLLM:
        async def generate_stream(self, messages, tools=None, **kwargs):
            yield StreamEvent(type="text", delta="answer")
            yield StreamEvent(
                type="finish",
                finish_reason="stop",
                usage=TokenUsage(prompt_tokens=4, completion_tokens=1, total_tokens=5),
            )

    monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_ENABLED", "1")
    monkeypatch.setenv("BOX_AGENT_SESSION_TRACE_DIR", str(tmp_path / "traces"))
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(max_steps=2, workspace_dir=str(tmp_path)),
        tools=ToolsConfig(enable_sub_agent=False),
    )
    agent = BoxACPAgent(DummyConn(), config, DoneLLM(), [], "system")
    session = await agent.newSession(
        SimpleNamespace(
            cwd=str(tmp_path),
            field_meta={"session_id": "office-session-current", "session_mode": "general"},
        )
    )

    assert session.sessionId.startswith("sess-0-")
    await agent.prompt(
        SimpleNamespace(
            sessionId=session.sessionId,
            prompt=[{"text": "user input"}],
            field_meta={"turn_id": "turn-current"},
        )
    )

    trace_path = tmp_path / "traces" / "office-session-current.jsonl"
    records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert all(record["session_id"] == "office-session-current" for record in records)
    assert all(record["acp_session_id"] == session.sessionId for record in records)
    assert {record["event"] for record in records} >= {
        "session.start",
        "turn.input",
        "turn.output",
        "turn.end",
    }
    turn_records = [record for record in records if record["event"].startswith("turn.")]
    assert all(record["turn_id"] == "turn-current" for record in turn_records)
