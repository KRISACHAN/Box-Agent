import json
from pathlib import Path

from box_agent.schema import Message
from box_agent.tool_result_storage import (
    DEFAULT_MAX_RESULT_SIZE_CHARS,
    DEFAULT_TOOL_RESULTS_BUDGET_CHARS,
    ToolResultStorage,
    generate_preview,
)
from box_agent.tools.base import Tool
from box_agent.tools.file.read_tool import ReadTool


class _Tool(Tool):
    @property
    def name(self) -> str:
        return "bash"


def _message(content, tool_call_id="call-1", name="bash") -> Message:
    return Message(
        role="tool",
        content=content,
        tool_call_id=tool_call_id,
        name=name,
    )


def test_default_limits_are_20k_per_result_and_50k_per_fresh_batch() -> None:
    assert DEFAULT_MAX_RESULT_SIZE_CHARS == 20_000
    assert DEFAULT_TOOL_RESULTS_BUDGET_CHARS == 50_000


def test_generate_preview_prefers_nearby_newline_and_marks_more() -> None:
    content = "a" * 1_500 + "\n" + "b" * 1_000
    preview, has_more = generate_preview(content)

    assert preview == "a" * 1_500
    assert has_more is True


def test_generate_preview_uses_exact_limit_when_newline_is_too_early() -> None:
    content = "short\n" + "x" * 3_000
    preview, has_more = generate_preview(content)

    assert len(preview) == 2_000
    assert has_more is True


def test_immediate_large_string_is_written_once_and_replaced(tmp_path: Path) -> None:
    storage = ToolResultStorage(tmp_path, default_result_limit=10)
    original = _message("line one\n" + "x" * 2_500)

    first = storage.process_message(original, tool=_Tool(), session_id="session-a")
    path = tmp_path / "session-a" / "tool-results" / "call-1.txt"
    assert path.read_text(encoding="utf-8") == original.content
    assert first.content.startswith("<persisted-output>\n")
    assert str(path) in first.content
    assert "\n...\n</persisted-output>" in first.content

    path.write_text("sentinel", encoding="utf-8")
    second = storage.process_message(original, tool=_Tool(), session_id="session-a")
    assert path.read_text(encoding="utf-8") == "sentinel"
    assert second.content == first.content


def test_complete_tool_payload_is_persisted_instead_of_bounded_host_view(
    tmp_path: Path,
) -> None:
    storage = ToolResultStorage(tmp_path, default_result_limit=10)
    bounded = _message("bounded host preview")
    complete = "complete beginning\n" + "x" * 2_500 + "\ncomplete end"

    result = storage.process_message(
        bounded,
        tool=_Tool(),
        session_id="session-a",
        persistence_content=complete,
    )

    path = tmp_path / "session-a" / "tool-results" / "call-1.txt"
    assert path.read_text(encoding="utf-8") == complete
    assert result.content.startswith("<persisted-output>")
    assert "Tool-bounded output" in result.content
    assert "bounded host preview" in result.content
    assert "complete beginning" not in result.content


def test_processed_model_context_is_not_persisted_or_reprocessed(
    tmp_path: Path,
) -> None:
    storage = ToolResultStorage(
        tmp_path,
        default_result_limit=5,
        aggregate_budget=5,
    )
    processed = _message("compact semantic context", tool_call_id="semantic-1")

    immediate = storage.process_message(
        processed,
        tool=_Tool(),
        session_id="session-a",
        content_already_processed=True,
    )
    messages = [immediate]
    aggregate = storage.enforce_fresh_budget(
        messages,
        tools={"bash": _Tool()},
        session_id="session-a",
    )

    assert immediate is processed
    assert aggregate.fresh_count == 0
    assert messages[0].content == "compact semantic context"
    assert not (tmp_path / "session-a" / "tool-results").exists()


def test_text_block_array_is_json_but_non_text_blocks_are_preserved(tmp_path: Path) -> None:
    storage = ToolResultStorage(tmp_path, default_result_limit=5)
    text_blocks = _message([{"type": "text", "text": "large text"}])
    persisted = storage.process_message(text_blocks, tool=_Tool(), session_id="s")
    path = tmp_path / "s" / "tool-results" / "call-1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == text_blocks.content
    assert "<persisted-output>" in persisted.content

    image = _message(
        [{"type": "image", "source": {"type": "base64", "data": "x" * 100}}],
        tool_call_id="call-image",
    )
    assert storage.process_message(image, tool=_Tool(), session_id="s") is image
    assert not (tmp_path / "s" / "tool-results" / "call-image.json").exists()


def test_read_is_infinite_and_empty_output_gets_marker(tmp_path: Path) -> None:
    storage = ToolResultStorage(tmp_path, default_result_limit=5)
    read = ReadTool(workspace_dir=str(tmp_path))
    large = _message("x" * 1_000, name="read_file")
    empty = _message("  \n", tool_call_id="empty")

    assert storage.process_message(large, tool=read, session_id="s") is large
    assert storage.process_message(empty, tool=_Tool()).content == "(Bash completed with no output)"


def test_persistence_failure_keeps_original(tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    storage = ToolResultStorage(blocker, default_result_limit=5)
    original = _message("x" * 100)

    assert storage.process_message(original, tool=_Tool(), session_id="s") is original


def test_fresh_aggregate_budget_persists_largest_then_freezes_ids(tmp_path: Path) -> None:
    storage = ToolResultStorage(
        tmp_path,
        default_result_limit=1_000,
        aggregate_budget=100,
    )
    messages = [
        _message("a" * 80, "a"),
        _message("b" * 60, "b"),
        _message("c" * 40, "c"),
    ]
    tools = {"bash": _Tool()}

    first = storage.enforce_fresh_budget(messages, tools=tools, session_id="s")
    assert first.fresh_count == 3
    assert first.persisted_count == 1
    assert first.remaining_chars == 100
    assert "<persisted-output>" in messages[0].content
    assert messages[1].content == "b" * 60

    messages[1] = _message("b" * 500, "b")
    second = storage.enforce_fresh_budget(messages, tools=tools, session_id="s")
    assert second.fresh_count == 0
    assert second.persisted_count == 0
    assert messages[1].content == "b" * 500


def test_aggregate_budget_never_persists_read_results(tmp_path: Path) -> None:
    storage = ToolResultStorage(tmp_path, aggregate_budget=10)
    messages = [_message("x" * 1_000, "read-1", "read_file")]

    outcome = storage.enforce_fresh_budget(
        messages,
        tools={"read_file": ReadTool(workspace_dir=str(tmp_path))},
        session_id="s",
    )

    assert outcome.persisted_count == 0
    assert messages[0].content == "x" * 1_000


def test_existing_history_is_frozen_when_conversation_state_is_initialized(tmp_path: Path) -> None:
    storage = ToolResultStorage(tmp_path, aggregate_budget=10)
    historical = _message("x" * 1_000, "old")
    messages = [historical]
    storage.initialize_history(messages)

    outcome = storage.enforce_fresh_budget(
        messages,
        tools={"bash": _Tool()},
        session_id="s",
    )

    assert outcome.fresh_count == 0
    assert messages[0] is historical
