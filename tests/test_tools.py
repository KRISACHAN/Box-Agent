"""Test cases for tools."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.tools import BashTool, EditTool, ReadTool, WriteTool, add_workspace_tools
from box_agent.tools.file_tools import truncate_text_by_tokens


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
            "truncated": False,
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
        "truncated": False,
    }


def test_read_truncation_marker_is_stable():
    truncated = truncate_text_by_tokens("token " * 40_000, 32_000)

    assert "[Content truncated:" in truncated
    assert "tokens -> ~32000 tokens limit" in truncated


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
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(workspace_dir=str(tmp_path)),
        tools=ToolsConfig(
            enable_bash=False,
            enable_skills=False,
            enable_mcp=True,
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
