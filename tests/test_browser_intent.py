from __future__ import annotations

import pytest

from box_agent.events import ToolCallResult
from box_agent.runtime import run_agent_loop
from box_agent.schema import FunctionCall, LLMResponse, Message, StreamEvent, ToolCall
from box_agent.tools.base import Tool, ToolResult
from box_agent.tools.browser_intent import (
    BrowserToolIntentPolicy,
    has_explicit_current_page_intent,
)


@pytest.mark.parametrize(
    "user_text",
    [
        "看一下当前页面里的两个选项",
        "帮我总结这个网页",
        "读取我浏览器里打开的页面",
        "对比我已经登录后的页面",
        "总结这篇公众号文章",
        "summarize the current browser tab",
        "compare the options on this page",
    ],
)
def test_current_page_intent_accepts_explicit_page_references(user_text: str) -> None:
    assert has_explicit_current_page_intent(user_text)


@pytest.mark.parametrize(
    "user_text",
    [
        "看一下gpt sol 极高和最高的区别",
        "帮我看看这个问题",
        "查一下最新资料",
        "了解一下这个模型",
        "打开 https://example.com 并总结",
        "做一个网页",
        "compare GPT modes",
    ],
)
def test_current_page_intent_rejects_generic_requests(user_text: str) -> None:
    assert not has_explicit_current_page_intent(user_text)


def test_browser_continuation_requires_recent_successful_browser_context() -> None:
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="看看当前页面"),
        Message(role="assistant", content=""),
        Message(
            role="tool",
            name="browser_read_current_page",
            tool_call_id="browser-1",
            content='{"ok": true}',
        ),
        Message(role="user", content="继续看"),
    ]

    policy = BrowserToolIntentPolicy.for_turn(
        current_turn_text="继续看",
        messages=messages,
    )

    assert policy.allow_current_page is True
    messages[-2] = messages[-2].model_copy(update={"content": "Error: source_unavailable"})
    failed_policy = BrowserToolIntentPolicy.for_turn(
        current_turn_text="继续看",
        messages=messages,
    )
    assert failed_policy.allow_current_page is False


def test_browser_policy_blocks_current_page_aliases_without_explicit_intent() -> None:
    policy = BrowserToolIntentPolicy.for_turn(
        current_turn_text="看一下gpt sol 极高和最高的区别",
        messages=[],
    )

    assert policy.is_tool_visible("browser_read_current_page") is False
    assert policy.is_tool_visible("browser_connector_snapshot") is False
    assert policy.is_tool_visible("browser_open_url") is True
    assert policy.tool_call_error("browser_read_page", {}) is not None
    assert policy.tool_call_error("browser_read_page", {"url": "https://example.com"}) is None
    assert (
        policy.tool_call_error(
            "browser_session_call",
            {"action": "read_article", "args": {}},
        )
        is not None
    )


class _CapturingLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.tool_name_calls: list[list[str]] = []

    async def generate_stream(self, messages, tools=None, **_):
        self.tool_name_calls.append([tool.name for tool in tools or []])
        response = self._responses.pop(0)
        if response.content:
            yield StreamEvent(type="text", delta=response.content)
        yield StreamEvent(
            type="finish",
            finish_reason=response.finish_reason,
            tool_calls=response.tool_calls,
        )


class _CountingCurrentPageTool(Tool):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "browser_read_current_page"

    @property
    def description(self) -> str:
        return "Read the current browser page"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self) -> ToolResult:
        self.calls += 1
        return ToolResult(success=True, content='{"ok": true}')


def _current_page_call() -> ToolCall:
    return ToolCall(
        id="browser-call",
        type="function",
        function=FunctionCall(name="browser_read_current_page", arguments={}),
    )


async def _collect_events(iterator):
    return [event async for event in iterator]


@pytest.mark.asyncio
async def test_core_hides_and_denies_current_page_tool_for_generic_request() -> None:
    tool = _CountingCurrentPageTool()
    llm = _CapturingLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[_current_page_call()],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="直接回答", finish_reason="stop"),
        ]
    )

    events = await _collect_events(
        run_agent_loop(
            llm=llm,
            messages=[
                Message(role="system", content="system"),
                Message(role="user", content="看一下gpt sol 极高和最高的区别"),
            ],
            tools={tool.name: tool},
            max_steps=3,
            current_turn_text="看一下gpt sol 极高和最高的区别",
        )
    )

    assert "browser_read_current_page" not in llm.tool_name_calls[0]
    assert tool.calls == 0
    result = next(event for event in events if isinstance(event, ToolCallResult))
    assert result.success is False
    assert result.user_visible is False
    assert "CURRENT_PAGE_INTENT_REQUIRED" in (result.error or "")


@pytest.mark.asyncio
async def test_core_exposes_and_executes_current_page_tool_for_explicit_request() -> None:
    tool = _CountingCurrentPageTool()
    llm = _CapturingLLM(
        [
            LLMResponse(
                content="",
                tool_calls=[_current_page_call()],
                finish_reason="tool_calls",
            ),
            LLMResponse(content="已读取", finish_reason="stop"),
        ]
    )

    events = await _collect_events(
        run_agent_loop(
            llm=llm,
            messages=[
                Message(role="system", content="system"),
                Message(role="user", content="看一下当前页面里的两个选项"),
            ],
            tools={tool.name: tool},
            max_steps=3,
            current_turn_text="看一下当前页面里的两个选项",
        )
    )

    assert "browser_read_current_page" in llm.tool_name_calls[0]
    assert tool.calls == 1
    result = next(event for event in events if isinstance(event, ToolCallResult))
    assert result.success is True
    assert result.user_visible is True
