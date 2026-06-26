"""Test cases for SubAgentTool."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from box_agent.events import DoneEvent, StopReason, SubAgentEvent, WebSearchEvent
from box_agent.schema import LLMResponse, Message, StreamEvent
from box_agent.agent import Agent
from box_agent.tools.base import Tool, ToolResult
from box_agent.tools.sub_agent_tool import SubAgentTool


# ── Helpers ──────────────────────────────────────────────────


class DummyTool(Tool):
    """A trivial tool for tests."""

    @property
    def name(self) -> str:
        return "dummy"

    @property
    def description(self) -> str:
        return "A dummy tool"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, content="dummy result")


class WebSearchTool(Tool):
    """A web_search-shaped tool that returns reference metadata."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"query": {"type": "string"}}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=True,
            content='{"refs":[{"reference_tag":"ref_1","title":"Example","url":"https://example.com"}]}',
        )


def _make_llm(text: str = "summary", tool_calls=None):
    """Return a mock LLM whose generate_stream yields the given text then finishes."""
    llm = AsyncMock()

    async def fake_stream(*, messages, tools, **kwargs):
        yield StreamEvent(type="text", delta=text)
        yield StreamEvent(
            type="finish",
            finish_reason="stop" if not tool_calls else "tool_use",
            tool_calls=tool_calls,
        )

    llm.generate_stream = fake_stream
    return llm


# ── Basic properties ─────────────────────────────────────────


def test_name():
    llm = AsyncMock()
    tool = SubAgentTool(llm=llm, parent_tools={})
    assert tool.name == "sub_agent"


def test_parallel_safe():
    llm = AsyncMock()
    tool = SubAgentTool(llm=llm, parent_tools={})
    assert tool.parallel_safe is True


def test_default_parallel_safe_is_false():
    """Other tools should have parallel_safe == False by default."""
    dummy = DummyTool()
    assert dummy.parallel_safe is False


def test_schema():
    llm = AsyncMock()
    tool = SubAgentTool(llm=llm, parent_tools={})
    schema = tool.to_schema()
    assert schema["name"] == "sub_agent"
    assert "task" in schema["input_schema"]["properties"]
    # `title` is an optional short distinct label, not required.
    assert "title" in schema["input_schema"]["properties"]
    assert schema["input_schema"]["required"] == ["task"]

    openai_schema = tool.to_openai_schema()
    assert openai_schema["function"]["name"] == "sub_agent"


def test_description_encourages_bounded_parallel_units_with_parent_merge():
    llm = AsyncMock()
    tool = SubAgentTool(llm=llm, parent_tools={})
    description = tool.description

    assert "Mandatory trigger" in description
    assert "independent evidence gathering" in description
    assert "fact checking" in description
    assert "analysis, comparison, drafting" in description
    assert "more than 5 structurally similar units" in description
    assert "launch 3-7 sub_agent calls first" in description
    assert "single small unit" in description
    assert "1 candidate" in description
    assert "1 source range" in description
    assert "1 sub-question" in description
    assert "unique path, directory, or filename prefix" in description
    assert "If the final deliverable is a single file" in description
    assert "draft fragments, local partial files" in description
    assert "evidence/finding summaries" in description
    assert "Do not assign two sub-agents to write the same file" in description
    assert "parent agent must own coordination" in description
    assert "write final deliverables" in description


# ── Tool filtering ───────────────────────────────────────────


def test_child_tools_exclude_sub_agent():
    """SubAgentTool must not include itself in the child tool set."""
    llm = AsyncMock()
    dummy = DummyTool()
    parent = {"dummy": dummy, "sub_agent": SubAgentTool(llm=llm, parent_tools={})}
    tool = SubAgentTool(llm=llm, parent_tools=parent)
    resolved = tool._resolve_child_tools()
    assert "sub_agent" not in resolved
    assert "dummy" in resolved


def test_resolve_child_tools_prefers_live_provider():
    """Child toolset follows the parent's live tool map, not the snapshot.

    Tools registered after construction (e.g. MCP web_search merged in via
    register_mcp_tools) must be inherited by child agents.
    """
    llm = AsyncMock()
    snapshot = {"dummy": DummyTool()}
    tool = SubAgentTool(llm=llm, parent_tools=snapshot)

    # Live parent map gains a tool after construction; provider points at it.
    live: dict = {"dummy": DummyTool(), "sub_agent": tool}
    tool.set_tool_provider(lambda: live)
    live["web_search"] = DummyTool()  # simulate late MCP merge (in-place mutation)

    resolved = tool._resolve_child_tools()
    assert "web_search" in resolved  # late tool inherited
    assert "sub_agent" not in resolved  # still excludes itself


def test_resolve_child_tools_falls_back_to_snapshot():
    """Without a provider (or if it fails), fall back to the snapshot."""
    llm = AsyncMock()
    tool = SubAgentTool(llm=llm, parent_tools={"dummy": DummyTool()})
    assert "dummy" in tool._resolve_child_tools()  # no provider → snapshot

    tool.set_tool_provider(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "dummy" in tool._resolve_child_tools()  # provider raised → snapshot


# ── Execution ────────────────────────────────────────────────


async def test_basic_execution():
    """Sub-agent returns the LLM's final text as ToolResult content."""
    llm = _make_llm(text="Analysis complete: revenue up 20%")
    tool = SubAgentTool(llm=llm, parent_tools={})
    result = await tool.execute(task="Analyze revenue data")
    assert result.success is True
    assert "revenue up 20%" in result.content


async def test_forwarded_events_carry_short_title():
    """A provided `title` becomes the SubAgentEvent label; task is unchanged."""
    llm = _make_llm(text="done")
    tool = SubAgentTool(llm=llm, parent_tools={})
    queue = asyncio.Queue()
    tool._event_queue = queue
    tool._parent_tool_call_id = "parent-sub-agent"

    await tool.execute(
        task="围绕商汤科技（SenseTime, 0020.HK）做一个独立研究切片：财务表现与业务结构",
        title="财务表现与业务结构",
    )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    sub_events = [e for e in events if isinstance(e, SubAgentEvent)]
    assert sub_events
    assert all(e.title == "财务表现与业务结构" for e in sub_events)
    # task_preview still reflects the (long, shared-prefix) task.
    assert all(e.title != e.task_preview for e in sub_events)


async def test_title_falls_back_to_task_preview_when_omitted():
    """Without a title, the label falls back to the task preview (no break)."""
    llm = _make_llm(text="done")
    tool = SubAgentTool(llm=llm, parent_tools={})
    queue = asyncio.Queue()
    tool._event_queue = queue
    tool._parent_tool_call_id = "parent-sub-agent"

    await tool.execute(task="Analyze revenue data for Q3")

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    sub_events = [e for e in events if isinstance(e, SubAgentEvent)]
    assert sub_events
    assert all(e.title == e.task_preview for e in sub_events)


async def test_sub_agent_inherits_parent_system_prompt_constraints():
    """Child system prompt includes finalized parent instructions automatically."""
    captured_messages = None

    async def fake_stream(*, messages, tools, **kwargs):
        nonlocal captured_messages
        captured_messages = messages
        yield StreamEvent(type="text", delta="done")
        yield StreamEvent(type="finish", finish_reason="stop", tool_calls=None)

    llm = AsyncMock()
    llm.generate_stream = fake_stream

    parent_prompt = "Parent constraint: write drafts under draft-a/ only."
    tool = SubAgentTool(llm=llm, parent_tools={})
    tool.set_parent_system_prompt(parent_prompt)

    result = await tool.execute(task="Draft one isolated section")

    assert result.success is True
    assert captured_messages is not None
    child_system_prompt = captured_messages[0].content
    assert "Inherited parent system prompt" in child_system_prompt
    assert parent_prompt in child_system_prompt
    assert "Do not overwrite shared files or final deliverables" in child_system_prompt


def test_agent_wires_system_prompt_into_sub_agent(tmp_path):
    """Agent initialization attaches its finalized system prompt to SubAgentTool."""
    llm = AsyncMock()
    tool = SubAgentTool(llm=llm, parent_tools={})

    Agent(
        llm_client=llm,
        system_prompt="Parent constraint: keep output generic.",
        tools=[tool],
        workspace_dir=str(tmp_path),
    )

    assert tool._parent_system_prompt is not None
    assert "Parent constraint: keep output generic." in tool._parent_system_prompt
    assert "Current Workspace" in tool._parent_system_prompt


async def test_web_search_tool_emits_reference_event():
    """web_search tool results should surface refs as a structured event."""
    from box_agent.core import run_agent_loop
    from box_agent.schema import FunctionCall, ToolCall

    call_num = 0

    async def fake_stream(*, messages, tools, **kwargs):
        nonlocal call_num
        call_num += 1
        if call_num == 1:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="search-1",
                        type="function",
                        function=FunctionCall(name="web_search", arguments={"query": "example"}),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="summary [ref_1]")
            yield StreamEvent(type="finish", finish_reason="stop", tool_calls=None)

    llm = AsyncMock()
    llm.generate_stream = fake_stream

    events = []
    async for event in run_agent_loop(
        llm=llm,
        messages=[Message(role="user", content="search")],
        tools={"web_search": WebSearchTool()},
        max_steps=3,
    ):
        events.append(event)

    web_events = [event for event in events if isinstance(event, WebSearchEvent)]
    assert len(web_events) == 1
    assert web_events[0].tool_call_id == "search-1"
    assert web_events[0].payload["refs"][0]["reference_tag"] == "ref_1"


async def test_sub_agent_forwards_web_search_reference_event():
    """Sub-agent child web_search refs should be forwarded to the parent stream."""
    from box_agent.schema import FunctionCall, ToolCall

    call_num = 0

    async def fake_stream(*, messages, tools, **kwargs):
        nonlocal call_num
        call_num += 1
        if call_num == 1:
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(
                        id="child-search-1",
                        type="function",
                        function=FunctionCall(name="web_search", arguments={"query": "example"}),
                    )
                ],
            )
        else:
            yield StreamEvent(type="text", delta="child summary [ref_1]")
            yield StreamEvent(type="finish", finish_reason="stop", tool_calls=None)

    llm = AsyncMock()
    llm.generate_stream = fake_stream

    tool = SubAgentTool(llm=llm, parent_tools={"web_search": WebSearchTool()})

    queue = asyncio.Queue()
    tool._event_queue = queue
    tool._parent_tool_call_id = "parent-sub-agent"

    result = await tool.execute(task="search in child")

    forwarded = []
    while not queue.empty():
        forwarded.append(queue.get_nowait())

    assert result.success is True
    web_events = [
        event
        for event in forwarded
        if isinstance(event, SubAgentEvent) and isinstance(event.event, WebSearchEvent)
    ]
    assert len(web_events) == 1
    assert web_events[0].parent_tool_call_id == "parent-sub-agent"
    assert web_events[0].sub_agent_id.startswith("subagent-")
    assert web_events[0].event.payload["refs"][0]["url"] == "https://example.com"


async def test_empty_output_returns_error():
    """If the LLM produces no content, the tool should report failure."""
    llm = _make_llm(text="")
    tool = SubAgentTool(llm=llm, parent_tools={})
    result = await tool.execute(task="Do something")
    assert result.success is False
    assert "without producing output" in result.error


async def test_llm_exception_returns_error():
    """If the LLM raises, ToolResult should contain the error info."""
    llm = AsyncMock()

    async def boom(*, messages, tools, **kwargs):
        raise RuntimeError("API timeout")
        yield  # make it an async generator  # noqa: E501

    llm.generate_stream = boom
    tool = SubAgentTool(llm=llm, parent_tools={})
    result = await tool.execute(task="Try this")
    # run_agent_loop catches the exception and yields DoneEvent with error as final_content,
    # so SubAgentTool wraps it as a successful result containing the error text.
    # The error is humanized via classify_llm_error: "API timeout" classifies as a
    # timeout, so the friendly Chinese message is surfaced rather than the raw string.
    assert "超时" in result.content


async def test_max_steps_respected():
    """Sub-agent should stop after max_steps even if LLM keeps requesting tools."""
    from box_agent.schema import FunctionCall, ToolCall

    call_count = 0

    async def looping_stream(*, messages, tools, **kwargs):
        nonlocal call_count
        call_count += 1
        # Always request a tool call to keep the loop going
        tc = ToolCall(
            id=f"tc-{call_count}",
            type="function",
            function=FunctionCall(name="dummy", arguments={}),
        )
        yield StreamEvent(type="text", delta=f"step {call_count}")
        yield StreamEvent(type="finish", finish_reason="tool_use", tool_calls=[tc])

    llm = AsyncMock()
    llm.generate_stream = looping_stream

    dummy = DummyTool()
    tool = SubAgentTool(
        llm=llm,
        parent_tools={"dummy": dummy},
        max_steps=3,
    )
    result = await tool.execute(task="Loop forever")
    # Should have stopped — call_count should be capped at max_steps
    assert call_count <= 4  # max_steps=3 means 3 LLM calls


# ── Parallel execution in core ───────────────────────────────


async def test_parallel_execution_in_core():
    """Multiple parallel_safe tool calls should be gathered concurrently."""
    import asyncio
    from box_agent.core import run_agent_loop
    from box_agent.schema import FunctionCall, ToolCall

    execution_order = []

    class SlowSubAgent(Tool):
        parallel_safe = True

        @property
        def name(self) -> str:
            return "sub_agent"

        @property
        def description(self) -> str:
            return "test"

        @property
        def parameters(self) -> dict:
            return {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]}

        async def execute(self, task: str) -> ToolResult:
            execution_order.append(f"start:{task}")
            await asyncio.sleep(0.05)
            execution_order.append(f"end:{task}")
            return ToolResult(success=True, content=f"Done: {task}")

    # LLM: first call returns 2 sub_agent tool calls, second call ends
    call_num = 0

    async def fake_stream(*, messages, tools, **kwargs):
        nonlocal call_num
        call_num += 1
        if call_num == 1:
            yield StreamEvent(type="text", delta="Delegating")
            yield StreamEvent(
                type="finish",
                finish_reason="tool_use",
                tool_calls=[
                    ToolCall(id="tc-1", type="function", function=FunctionCall(name="sub_agent", arguments={"task": "A"})),
                    ToolCall(id="tc-2", type="function", function=FunctionCall(name="sub_agent", arguments={"task": "B"})),
                ],
            )
        else:
            yield StreamEvent(type="text", delta="All done")
            yield StreamEvent(type="finish", finish_reason="stop", tool_calls=None)

    llm = AsyncMock()
    llm.generate_stream = fake_stream

    messages = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Do two things"),
    ]
    tools = {"sub_agent": SlowSubAgent()}

    events = []
    async for event in run_agent_loop(llm=llm, messages=messages, tools=tools, max_steps=5):
        events.append(event)

    # Both starts should appear before either result (parallel execution)
    start_events = [e for e in events if hasattr(e, "tool_name") and hasattr(e, "arguments") and not hasattr(e, "success")]
    result_events = [e for e in events if hasattr(e, "success") and hasattr(e, "tool_name")]

    sub_starts = [e for e in start_events if e.tool_name == "sub_agent"]
    sub_results = [e for e in result_events if e.tool_name == "sub_agent"]

    assert len(sub_starts) == 2
    assert len(sub_results) == 2

    # Verify parallel execution: both starts happen before both ends
    assert execution_order[0].startswith("start:")
    assert execution_order[1].startswith("start:")


def test_add_workspace_tools_wires_sub_agent_token_limit(tmp_path) -> None:
    """config.agent.sub_agent_token_limit flows into the SubAgentTool instance."""
    from box_agent.config import AgentConfig, ToolsConfig
    from box_agent.tools.setup import add_workspace_tools

    class Config:
        agent = AgentConfig(sub_agent_token_limit=12345)
        tools = ToolsConfig(
            enable_bash=False,
            enable_file_tools=False,
            enable_todo=False,
            enable_sub_agent=True,
        )

    tools: list = []
    add_workspace_tools(
        tools,
        Config(),
        tmp_path,
        allow_full_access=False,
        llm=AsyncMock(),
        output=lambda *_: None,
    )

    sub_agent = next(t for t in tools if t.name == "sub_agent")
    assert sub_agent._token_limit == 12345
