"""Test cases for tools."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.tools import (
    AppendTool,
    BashTool,
    EditTool,
    ReadTool,
    SearchFilesTool,
    WriteTool,
    add_workspace_tools,
)
from box_agent.tools.file_tools import MAX_SEARCH_OFFSET, MAX_SEARCH_OUTPUT_CHARS
from box_agent.tools.permissions import CapabilityPolicy, PermissionEngine


@pytest.mark.asyncio
async def test_read_tool():
    """Test read file tool."""
    print("\n=== Testing ReadTool ===")

    # Create a temp file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Hello, World!")
        temp_path = f.name

    try:
        tool = ReadTool()
        result = await tool.execute(path=temp_path)

        assert result.success, f"Read failed: {result.error}"
        # ReadTool now returns content with line numbers in format: "LINE_NUMBER|LINE_CONTENT"
        assert "Hello, World!" in result.content, f"Content mismatch: {result.content}"
        assert "|Hello, World!" in result.content, f"Expected line number format: {result.content}"
        assert result.raw_output == {
            "source_char_count": len("Hello, World!"),
            "selected_char_count": len("Hello, World!"),
            "selected_line_count": 1,
            "total_lines": 1,
            "truncated": False,
            "has_more": False,
            "next_offset": None,
        }
        print("✅ ReadTool test passed")
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_read_tool_reports_selected_range_completeness(tmp_path):
    path = tmp_path / "range.txt"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = await ReadTool(workspace_dir=str(tmp_path)).execute(
        path="range.txt",
        offset=2,
        limit=1,
    )

    assert result.success is True
    assert result.raw_output == {
        "source_char_count": len("one\ntwo\nthree\n"),
        "selected_char_count": len("two\n"),
        "selected_line_count": 1,
        "total_lines": 3,
        "truncated": False,
        "has_more": True,
        "next_offset": 3,
    }


@pytest.mark.asyncio
async def test_read_tool_defaults_to_bounded_page_with_continuation_hint(tmp_path):
    path = tmp_path / "large.txt"
    path.write_text("".join(f"line-{index}\n" for index in range(1, 601)), encoding="utf-8")

    result = await ReadTool(workspace_dir=str(tmp_path)).execute(path="large.txt")

    assert result.success is True
    assert "line-500" in result.content
    assert "line-501" not in result.content
    assert "Use offset=501, limit=500 to continue" in result.content
    assert result.raw_output["selected_line_count"] == 500
    assert result.raw_output["total_lines"] == 600
    assert result.raw_output["next_offset"] == 501


@pytest.mark.asyncio
async def test_read_tool_rejects_oversized_page_instead_of_truncating_middle(tmp_path):
    path = tmp_path / "long-line.txt"
    path.write_text("x" * 100_001, encoding="utf-8")

    result = await ReadTool(workspace_dir=str(tmp_path)).execute(path="long-line.txt")

    assert result.success is False
    assert "100,000-character safety limit" in result.error
    assert "smaller limit" in result.error
    assert "Content truncated" not in result.error


@pytest.mark.asyncio
async def test_read_tool_rejects_binary_and_directory_paths(tmp_path):
    binary = tmp_path / "payload.bin"
    binary.write_bytes(b"\x00\x01\x02")
    tool = ReadTool(workspace_dir=str(tmp_path))

    binary_result = await tool.execute(path="payload.bin")
    directory_result = await tool.execute(path=".")

    assert binary_result.success is False
    assert "binary file" in binary_result.error
    assert directory_result.success is False
    assert "Use search_files" in directory_result.error


@pytest.mark.asyncio
async def test_search_files_lists_and_searches_without_bash(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("alpha\nneedle here\nomega\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("needle docs\n", encoding="utf-8")
    tool = SearchFilesTool(workspace_dir=str(tmp_path))

    files_result = await tool.execute(pattern="*.py", target="files", path=".")
    content_result = await tool.execute(
        pattern="needle",
        target="content",
        path=".",
        file_glob="*.py",
    )

    assert files_result.success is True
    assert files_result.content == "src/app.py"
    assert content_result.success is True
    assert "src/app.py:2:>needle here" in content_result.content
    assert "README.md" not in content_result.content


@pytest.mark.asyncio
async def test_search_files_paginates_results(tmp_path):
    for index in range(5):
        (tmp_path / f"file-{index}.txt").write_text("value", encoding="utf-8")

    result = await SearchFilesTool(workspace_dir=str(tmp_path)).execute(
        pattern="*.txt",
        target="files",
        limit=2,
    )

    assert result.success is True
    assert result.raw_output["total_matches"] is None
    assert result.raw_output["matched_through"] == 3
    assert result.raw_output["total_is_exact"] is False
    assert result.raw_output["returned_matches"] == 2
    assert result.raw_output["next_offset"] == 2
    assert "more available" in result.content
    assert "Use offset=2, limit=2 to continue" in result.content


@pytest.mark.asyncio
async def test_search_files_stops_after_page_plus_one_match(tmp_path, monkeypatch):
    for index in range(100):
        (tmp_path / f"file-{index:03d}.txt").write_text("value", encoding="utf-8")
    tool = SearchFilesTool(workspace_dir=str(tmp_path))
    checked = 0

    def count_allowed(_path):
        nonlocal checked
        checked += 1
        return True

    monkeypatch.setattr(tool, "_file_allowed", count_allowed)
    result = await tool.execute(pattern="*.txt", target="files", limit=2)

    assert result.success is True
    assert checked == 3
    assert result.raw_output["scanned_files"] == 3
    assert result.raw_output["matched_through"] == 3
    assert result.raw_output["truncated"] is True


@pytest.mark.asyncio
async def test_search_files_bounds_total_output_and_paginates_from_returned_count(tmp_path):
    for index in range(60):
        (tmp_path / f"file-{index:03d}.txt").write_text(
            f"needle {'x' * 1_990}", encoding="utf-8"
        )

    result = await SearchFilesTool(workspace_dir=str(tmp_path)).execute(
        pattern="needle",
        target="content",
    )

    assert result.success is True
    assert len(result.content) <= MAX_SEARCH_OUTPUT_CHARS
    assert result.raw_output["output_limited"] is True
    assert result.raw_output["limit_reason"] == "output_budget"
    assert result.raw_output["returned_matches"] < 50
    assert result.raw_output["next_offset"] == result.raw_output["returned_matches"]
    assert "output budget reached" in result.content
    assert (
        f"Use offset={result.raw_output['next_offset']}, limit=50 to continue"
        in result.content
    )


@pytest.mark.asyncio
async def test_search_files_rejects_offset_above_bounded_maximum(tmp_path):
    result = await SearchFilesTool(workspace_dir=str(tmp_path)).execute(
        pattern="*.txt",
        target="files",
        offset=MAX_SEARCH_OFFSET + 1,
    )

    assert result.success is False
    assert f"at most {MAX_SEARCH_OFFSET:,}" in result.error


@pytest.mark.asyncio
async def test_search_files_discards_matches_before_offset(tmp_path, monkeypatch):
    for index in range(8):
        (tmp_path / f"file-{index}.txt").write_text("value", encoding="utf-8")
    tool = SearchFilesTool(workspace_dir=str(tmp_path))
    retained_page_sizes = []
    original_search = tool._search_sync

    def observe_page(**kwargs):
        scan = original_search(**kwargs)
        retained_page_sizes.append(len(scan["selected"]))
        return scan

    monkeypatch.setattr(tool, "_search_sync", observe_page)
    result = await tool.execute(
        pattern="*.txt",
        target="files",
        offset=5,
        limit=2,
    )

    assert result.success is True
    assert retained_page_sizes == [2]
    assert "file-5.txt" in result.content
    assert "file-0.txt" not in result.content


@pytest.mark.asyncio
async def test_search_files_files_only_paginates_unique_files(tmp_path):
    (tmp_path / "a.txt").write_text("needle\nneedle\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("needle\n", encoding="utf-8")

    result = await SearchFilesTool(workspace_dir=str(tmp_path)).execute(
        pattern="needle",
        target="content",
        output_mode="files_only",
        limit=2,
    )

    assert result.success is True
    assert result.content.count("a.txt") == 1
    assert "b.txt" in result.content
    assert "c.txt" not in result.content
    assert result.raw_output["matched_through"] == 3
    assert result.raw_output["next_offset"] == 2


@pytest.mark.asyncio
async def test_search_files_count_mode_streams_and_paginates_file_counts(tmp_path):
    (tmp_path / "a.txt").write_text("needle\nneedle\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("needle\n", encoding="utf-8")
    (tmp_path / "c.txt").write_text("needle\nneedle\nneedle\n", encoding="utf-8")

    result = await SearchFilesTool(workspace_dir=str(tmp_path)).execute(
        pattern="needle",
        target="content",
        output_mode="count",
        offset=1,
        limit=1,
    )

    assert result.success is True
    assert result.content.startswith("b.txt:1")
    assert "a.txt" not in result.content
    assert "c.txt" not in result.content
    assert result.raw_output["matched_through"] == 3
    assert result.raw_output["returned_matches"] == 1
    assert result.raw_output["next_offset"] == 2


@pytest.mark.asyncio
async def test_search_files_timeout_returns_bounded_partial_result(tmp_path, monkeypatch):
    for index in range(10):
        (tmp_path / f"file-{index}.txt").write_text("value", encoding="utf-8")
    tool = SearchFilesTool(
        workspace_dir=str(tmp_path),
        search_timeout_seconds=0.02,
        heartbeat_seconds=0.01,
    )

    def slow_allowed(_path):
        import time

        time.sleep(0.03)
        return True

    monkeypatch.setattr(tool, "_file_allowed", slow_allowed)
    result = await tool.execute(pattern="*.txt", target="files", limit=5)

    assert result.success is True
    assert result.raw_output["timed_out"] is True
    assert result.raw_output["limit_reason"] == "search_timeout"
    assert result.raw_output["truncated"] is True
    assert "timed out" in result.content


@pytest.mark.asyncio
async def test_search_files_hard_timeout_returns_even_if_worker_is_stuck(tmp_path, monkeypatch):
    import time

    tool = SearchFilesTool(
        workspace_dir=str(tmp_path),
        search_timeout_seconds=0.02,
        heartbeat_seconds=0.01,
    )

    def stuck_worker(**_kwargs):
        time.sleep(0.2)
        return {
            "selected": [],
            "matched_results": 0,
            "scanned_files": 0,
            "has_more": False,
            "timed_out": False,
            "cancelled": False,
            "exact_total": True,
        }

    monkeypatch.setattr(tool, "_search_sync", stuck_worker)
    started = time.monotonic()
    result = await tool.execute(pattern="*.txt", target="files")

    assert time.monotonic() - started < 0.15
    assert result.success is True
    assert result.raw_output["timed_out"] is True


@pytest.mark.asyncio
async def test_search_files_emits_heartbeat_and_stops_worker_on_cancel(tmp_path, monkeypatch):
    import threading
    import time

    tool = SearchFilesTool(
        workspace_dir=str(tmp_path),
        search_timeout_seconds=5,
        heartbeat_seconds=0.01,
    )
    worker_stopped = threading.Event()

    def wait_for_cancel(**kwargs):
        stop_event = kwargs["stop_event"]
        while not stop_event.wait(0.005):
            pass
        worker_stopped.set()
        return {
            "selected": [],
            "matched_results": 0,
            "scanned_files": 0,
            "has_more": False,
            "timed_out": False,
            "cancelled": True,
            "exact_total": False,
        }

    monkeypatch.setattr(tool, "_search_sync", wait_for_cancel)
    queue = asyncio.Queue()
    task = asyncio.create_task(
        tool.execute_with_event_context(
            event_queue=queue,
            parent_tool_call_id="search-1",
            pattern="*.txt",
            target="files",
        )
    )

    await asyncio.sleep(0.03)
    assert not queue.empty()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(worker_stopped.wait, 1.0)


@pytest.mark.asyncio
async def test_search_files_returns_permission_request_for_host(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    engine = PermissionEngine(CapabilityPolicy(), workspace)
    outside = Path.home() / "box-agent-search-permission-probe"
    tool = SearchFilesTool(workspace_dir=str(workspace), permission_engine=engine)

    result = await tool.execute(pattern="*", target="files", path=str(outside))

    assert result.success is False
    assert result.permission_request is not None
    assert result.permission_request["scope"] == "filesystem"
    assert result.permission_request["path"] == str(outside)


def test_workspace_tools_register_search_files(tmp_path):
    config = Config(
        llm=LLMConfig(api_key="test"),
        agent=AgentConfig(workspace_dir=str(tmp_path)),
        tools=ToolsConfig(
            enable_bash=False,
            enable_todo=False,
            enable_plan=False,
            enable_sub_agent=False,
            enable_skills=False,
            enable_mcp=False,
        ),
    )
    tools = []

    add_workspace_tools(
        tools,
        config,
        tmp_path,
        allow_full_access=False,
        output=lambda *_: None,
        use_output_dir=False,
    )

    tool_names = {tool.name for tool in tools}
    assert "search_files" in tool_names
    assert "report_execution_result" in tool_names


@pytest.mark.asyncio
async def test_initialize_base_tools_can_gate_mcp_until_protocol_ready(
    tmp_path,
    monkeypatch,
):
    from box_agent.tools import setup as setup_module

    started = asyncio.Event()

    async def fake_load_mcp_tools_async(*args, **kwargs):
        started.set()
        return []

    monkeypatch.setattr(
        setup_module,
        "load_mcp_tools_async",
        fake_load_mcp_tools_async,
    )
    # Create a minimal MCP config file so the code path creates mcp_task.
    mcp_config = tmp_path / "mcp.json"
    mcp_config.write_text('{"mcpServers": {}}')
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(workspace_dir=str(tmp_path)),
        tools=ToolsConfig(
            enable_bash=False,
            enable_skills=False,
            enable_mcp=True,
            mcp_config_path=str(mcp_config),
        ),
    )
    gate = asyncio.Event()

    _, _, mcp_task, _ = await setup_module.initialize_base_tools(
        config,
        output=lambda *_: None,
        mcp_start_gate=gate,
    )
    assert mcp_task is not None
    await asyncio.sleep(0)
    assert started.is_set() is False

    gate.set()
    await mcp_task
    assert started.is_set() is True


@pytest.mark.asyncio
async def test_write_tool():
    """Test write file tool."""
    print("\n=== Testing WriteTool ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.txt"

        tool = WriteTool()
        result = await tool.execute(path=str(file_path), content="Test content")

        assert result.success, f"Write failed: {result.error}"
        assert file_path.exists(), "File was not created"
        assert file_path.read_text() == "Test content", "Content mismatch"
        print("✅ WriteTool test passed")


@pytest.mark.asyncio
async def test_write_tool_blocks_pptx_skipcheck_exporter():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "export_skipcheck.js"
        tool = WriteTool()
        result = await tool.execute(
            path=str(file_path),
            content='await window.domToPptx.exportToPptx([]); require("./dom-to-pptx.bundle.js");',
        )

        assert not result.success
        assert "PPTX HTML self-check bypass blocked" in result.error
        assert not file_path.exists()


@pytest.mark.asyncio
async def test_append_tool_allows_theme_css_after_canonical_pptx_comments(tmp_path):
    file_path = tmp_path / "common.css"
    file_path.write_text(
        "/* rejected by html_self_check.js / html_to_editable_pptx.js; "
        "everything below is yours to replace */\n"
        ".slide { width: 1920px; height: 1080px; }\n",
        encoding="utf-8",
    )

    result = await AppendTool().execute(
        path=str(file_path),
        content=".theme-dark { background: #05070d; }\n",
    )

    assert result.success, result.error
    assert file_path.read_text(encoding="utf-8").endswith(
        ".theme-dark { background: #05070d; }\n"
    )


@pytest.mark.asyncio
async def test_write_tool_rejects_model_history_placeholder():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "deck.html"
        tool = WriteTool()
        result = await tool.execute(
            path=str(file_path),
            content=(
                "[Full tool-call argument omitted from model history]\n"
                "Tool: write_file\n"
                "Argument: content\n"
                "Path: output/deck.html"
            ),
        )

        assert not result.success
        assert "model-history placeholder" in result.error
        assert not file_path.exists()


@pytest.mark.asyncio
async def test_edit_tool():
    """Test edit file tool."""
    print("\n=== Testing EditTool ===")

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        f.write("Hello, World!")
        temp_path = f.name

    try:
        tool = EditTool()
        result = await tool.execute(
            path=temp_path, old_str="World", new_str="Agent"
        )

        assert result.success, f"Edit failed: {result.error}"
        content = Path(temp_path).read_text()
        assert content == "Hello, Agent!", f"Content mismatch: {content}"
        print("✅ EditTool test passed")
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_edit_tool_rejects_model_history_placeholder():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".html") as f:
        f.write("<html><body>real</body></html>")
        temp_path = f.name

    try:
        tool = EditTool()
        result = await tool.execute(
            path=temp_path,
            old_str="real",
            new_str=(
                "[Full tool-call argument omitted from model history]\n"
                "Tool: edit_file\n"
                "Argument: new_str\n"
                f"Path: {temp_path}"
            ),
        )

        assert not result.success
        assert "model-history placeholder" in result.error
        assert Path(temp_path).read_text() == "<html><body>real</body></html>"
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_edit_tool_blocks_removing_pptx_self_check():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".js") as f:
        f.write('runSelfCheck(htmlPath, width, height, reportPath); require("./html_to_editable_pptx.js");')
        temp_path = f.name

    try:
        tool = EditTool()
        result = await tool.execute(
            path=temp_path,
            old_str="runSelfCheck(htmlPath, width, height, reportPath);",
            new_str="// removed to skip self-check",
        )

        assert not result.success
        assert "PPTX HTML self-check bypass blocked" in result.error
    finally:
        Path(temp_path).unlink()


@pytest.mark.asyncio
async def test_bash_tool():
    """Test bash command tool."""
    print("\n=== Testing BashTool ===")

    tool = BashTool()

    # Test successful command
    result = await tool.execute(command="echo 'Hello from bash'")
    assert result.success, f"Bash failed: {result.error}"
    assert "Hello from bash" in result.content, f"Output mismatch: {result.content}"
    print("✅ BashTool test passed")

    # Test failed command
    result = await tool.execute(command="exit 1")
    assert not result.success, "Command should have failed"
    print("✅ BashTool error handling test passed")


@pytest.mark.asyncio
async def test_bash_tool_blocks_lark_bot_identity_commands():
    tool = BashTool()

    for command in [
        'lark-cli config bind --identity bot-only',
        '$BOX_AGENT_LARK_CLI config bind --identity bot-only',
        'lark-cli config strict-mode bot',
        'lark-cli base +table-list --base-token abc --as bot',
    ]:
        result = await tool.execute(command=command)
        assert not result.success
        assert "Blocked:" in (result.error or "")


@pytest.mark.asyncio
async def test_bash_tool_requires_lark_business_commands_to_use_user_identity():
    tool = BashTool()

    result = await tool.execute(command='lark-cli base +table-list --base-token abc --format json')

    assert not result.success
    assert "must pass `--as user`" in (result.error or "")


@pytest.mark.asyncio
async def test_bash_tool_allows_setting_lark_cli_env_without_invoking_cli():
    tool = BashTool()

    result = await tool.execute(command='export BOX_AGENT_LARK_CLI=/tmp/lark-cli')

    assert result.success


@pytest.mark.asyncio
async def test_bash_tool_blocks_direct_obsidian_write_commands():
    tool = BashTool()

    for command in [
        "obsidian create path=t.md content=hi",
        "/usr/local/bin/obsidian append path=t.md content=hi",
        "$BOX_AGENT_OBSIDIAN_CLI open path=t.md",
        "obsidian daily:append content=hi",
    ]:
        result = await tool.execute(command=command)
        assert not result.success
        assert "obsidian_create_note" in (result.error or "")


@pytest.mark.asyncio
async def test_bash_tool_allows_obsidian_diagnostics():
    tool = BashTool()

    for command in [
        "which obsidian",
        "obsidian help",
        "obsidian version",
    ]:
        result = await tool.execute(command=command)
        # The command may fail when Obsidian CLI is not installed; the point is
        # that BashTool itself must not block diagnostics with the native-tool policy.
        assert "Blocked:" not in (result.error or "")


def test_add_workspace_tools_registers_obsidian_tools(tmp_path: Path):
    tools = []

    add_workspace_tools(
        tools,
        Config(
            llm=LLMConfig(api_key="test-key"),
            agent=AgentConfig(workspace_dir=str(tmp_path)),
            tools=ToolsConfig(enable_mcp=False),
        ),
        tmp_path,
        allow_full_access=False,
        output=lambda *_: None,
        llm=None,
    )

    names = {tool.name for tool in tools}
    assert "obsidian_create_note" in names
    assert "obsidian_update_note" in names
    assert "obsidian_daily_note" in names


async def main():
    """Run all tool tests."""
    print("=" * 80)
    print("Running Tool Tests")
    print("=" * 80)

    await test_read_tool()
    await test_write_tool()
    await test_edit_tool()
    await test_bash_tool()

    print("\n" + "=" * 80)
    print("All tool tests passed! ✅")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
