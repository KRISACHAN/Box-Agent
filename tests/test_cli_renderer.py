from __future__ import annotations

from box_agent.agent import Agent, Colors as AgentColors
from box_agent.cli_renderer import CliRenderer, Colors, _format_size
from box_agent.events import (
    ContentEvent,
    DoneEvent,
    StopReason,
    ToolCallResult,
    ToolCallStart,
)


def test_cli_renderer_preserves_basic_content_and_cancellation_output(capsys) -> None:
    renderer = CliRenderer()

    renderer.render(ContentEvent("hello"))
    renderer.render(DoneEvent(StopReason.CANCELLED, "ignored"))

    assert capsys.readouterr().out == (
        f"\n{Colors.BOLD}{Colors.BRIGHT_BLUE}🤖 Assistant:{Colors.RESET}\n"
        "hello\n"
        f"\n{Colors.BRIGHT_YELLOW}⚠️  Task cancelled by user.{Colors.RESET}\n"
    )


def test_cli_renderer_preserves_stream_flush_and_tool_visibility(capsys) -> None:
    renderer = CliRenderer()

    renderer.render(ContentEvent("stream", _streaming=True))
    assert renderer.streaming_active is True
    renderer.render(ToolCallStart("hidden", "bash", {"cmd": "pwd"}, user_visible=False))
    renderer.render(ToolCallStart("visible", "bash", {"cmd": "pwd"}))

    output = capsys.readouterr().out
    assert output.startswith("stream\n")
    assert "hidden" not in output
    assert f"{Colors.BRIGHT_YELLOW}🔧 Tool Call:{Colors.RESET}" in output
    assert '"cmd": "pwd"' in output
    assert renderer.streaming_active is False


def test_cli_renderer_renders_memory_search_results_and_size_labels(capsys) -> None:
    renderer = CliRenderer()

    renderer.render(
        ToolCallResult(
            "memory-1",
            "memory_search",
            True,
            "matched",
            raw_output={
                "type": "memory_search",
                "query": "preference",
                "matched_memories": [{"text": "Concise responses"}],
            },
        )
    )

    output = capsys.readouterr().out
    assert "✓ Result:" in output
    assert "🧠 Matched memories:" in output
    assert "Concise responses" in output
    assert _format_size(0) == "0B"
    assert _format_size(1024) == "1.0KB"
    assert _format_size(-1) == "?"


def test_agent_legacy_renderer_entrypoint_delegates_to_cli_renderer(capsys) -> None:
    agent = object.__new__(Agent)
    agent._streaming_active = False

    agent._render_event(ContentEvent("compatibility"))

    assert "compatibility" in capsys.readouterr().out
    assert AgentColors is Colors
