from pathlib import Path

import pytest

from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.tools.argument_limits import streamed_argument_limit
from box_agent.tools.file_tools import (
    AppendTool,
    EditTool,
    MAX_FILE_TOOL_CONTENT_CHARS,
    WriteTool,
)
from box_agent.tools.setup import SANDBOX_INFO_PROMPT, add_workspace_tools


def test_write_file_schema_has_no_content_size_limit_and_supports_chunks():
    content_schema = WriteTool().parameters["properties"]["content"]

    assert "maxLength" not in content_schema
    assert WriteTool().parameters["properties"]["chunk_index"]["default"] == 0
    assert WriteTool().parameters["properties"]["final"]["default"] is True
    assert streamed_argument_limit("write_file") is None


def test_append_file_schema_exposes_content_size_limit():
    content_schema = AppendTool().parameters["properties"]["content"]

    assert content_schema["maxLength"] == MAX_FILE_TOOL_CONTENT_CHARS
    assert f"{MAX_FILE_TOOL_CONTENT_CHARS:,} characters" in content_schema["description"]
    assert "multiple append calls" in content_schema["description"]


@pytest.mark.asyncio
async def test_write_file_writes_content_larger_than_the_legacy_limit(tmp_path):
    tool = WriteTool(workspace_dir=str(tmp_path))
    target = tmp_path / "output" / "large.html"
    content = "<!doctype html>\n" + ("x" * MAX_FILE_TOOL_CONTENT_CHARS)

    result = await tool.execute(path="output/large.html", content=content)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == content


@pytest.mark.asyncio
async def test_write_file_chunks_leave_target_unchanged_until_final_commit(tmp_path):
    target = tmp_path / "large.html"
    target.write_text("old", encoding="utf-8")
    tool = WriteTool(workspace_dir=str(tmp_path))

    first = await tool.execute(
        path="large.html", content="<html>", chunk_index=0, final=False
    )
    assert first.success is True
    assert target.read_text(encoding="utf-8") == "old"

    second = await tool.execute(
        path="large.html", content="</html>", chunk_index=1, final=True
    )
    assert second.success is True
    assert target.read_text(encoding="utf-8") == "<html></html>"
    assert second.raw_output["chunks"] == 2


@pytest.mark.asyncio
async def test_write_file_chunks_enforce_order_and_idempotent_retries(tmp_path):
    tool = WriteTool(workspace_dir=str(tmp_path))

    first = await tool.execute(path="a.txt", content="a", chunk_index=0, final=False)
    duplicate = await tool.execute(path="a.txt", content="a", chunk_index=0, final=False)
    skipped = await tool.execute(path="a.txt", content="c", chunk_index=2, final=True)

    assert first.success is True
    assert duplicate.success is True
    assert duplicate.raw_output["duplicate"] is True
    assert skipped.success is False
    assert skipped.error.startswith("WRITE_FILE_CHUNK_OUT_OF_ORDER")
    assert not (tmp_path / "a.txt").exists()


@pytest.mark.asyncio
async def test_append_file_appends_chunks_and_rejects_oversized_content(tmp_path):
    tool = AppendTool(workspace_dir=str(tmp_path))
    target = tmp_path / "output" / "large.html"

    first = await tool.execute(path="output/large.html", content="<html>")
    second = await tool.execute(path="output/large.html", content="<body>ok</body></html>")
    oversized = await tool.execute(
        path="output/large.html",
        content="x" * (MAX_FILE_TOOL_CONTENT_CHARS + 1),
    )

    assert first.success is True
    assert second.success is True
    assert target.read_text(encoding="utf-8") == "<html><body>ok</body></html>"
    assert oversized.success is False
    assert oversized.error is not None
    assert oversized.error.startswith("FILE_TOOL_ARGUMENT_TOO_LARGE")
    assert target.read_text(encoding="utf-8") == "<html><body>ok</body></html>"


def test_workspace_file_tools_expose_only_write_file_for_transactional_writes(tmp_path):
    tools = []
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_bash=False, enable_todo=False, enable_plan=False),
    )

    add_workspace_tools(tools, config, tmp_path)

    names = {tool.name for tool in tools}
    assert "append_file" in names
    assert "write_file" in names
    assert "staged_file_write" not in names


def test_sandbox_prompt_describes_write_file_chunk_protocol():
    assert "`write_file(path, content)`" in SANDBOX_INFO_PROMPT
    assert "chunk_index=0, final=false" in SANDBOX_INFO_PROMPT
    assert "`staged_file_write`" not in SANDBOX_INFO_PROMPT
    assert "禁止把文件正文、heredoc 或 base64 载荷塞进 `bash`" in SANDBOX_INFO_PROMPT


def test_system_prompt_describes_write_file_chunk_protocol():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "`write_file(path, content)`" in prompt
    assert "`chunk_index=0, final=false`" in prompt
    assert "`staged_file_write`" not in prompt
    assert "禁止把文件正文、heredoc 或 base64 载荷塞进 `bash`" in prompt


@pytest.mark.asyncio
async def test_edit_file_rejects_oversized_replacement(tmp_path):
    target = tmp_path / "sample.txt"
    target.write_text("old", encoding="utf-8")
    tool = EditTool(workspace_dir=str(tmp_path))

    result = await tool.execute(
        path="sample.txt",
        old_str="old",
        new_str="x" * (MAX_FILE_TOOL_CONTENT_CHARS + 1),
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("FILE_TOOL_ARGUMENT_TOO_LARGE")
    assert target.read_text(encoding="utf-8") == "old"
