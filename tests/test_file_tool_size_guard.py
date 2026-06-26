from pathlib import Path

import pytest

from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.tools.file_tools import AppendTool, MAX_FILE_TOOL_CONTENT_CHARS, WriteTool
from box_agent.tools.setup import SANDBOX_INFO_PROMPT, add_workspace_tools


def test_write_file_schema_exposes_content_size_limit():
    content_schema = WriteTool().parameters["properties"]["content"]

    assert content_schema["maxLength"] == MAX_FILE_TOOL_CONTENT_CHARS
    assert f"{MAX_FILE_TOOL_CONTENT_CHARS:,} characters" in content_schema["description"]
    assert "large generated artifacts" in content_schema["description"]
    assert "append_file for later chunks" in content_schema["description"]


def test_append_file_schema_exposes_content_size_limit():
    content_schema = AppendTool().parameters["properties"]["content"]

    assert content_schema["maxLength"] == MAX_FILE_TOOL_CONTENT_CHARS
    assert f"{MAX_FILE_TOOL_CONTENT_CHARS:,} characters" in content_schema["description"]
    assert "multiple append_file calls" in content_schema["description"]


@pytest.mark.asyncio
async def test_write_file_rejects_oversized_content_before_writing(tmp_path):
    tool = WriteTool(workspace_dir=str(tmp_path))
    target = tmp_path / "output" / "large.html"
    content = "<!doctype html>\n" + ("x" * MAX_FILE_TOOL_CONTENT_CHARS)

    result = await tool.execute(path="output/large.html", content=content)

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("FILE_TOOL_ARGUMENT_TOO_LARGE")
    assert "Use write_file for the first chunk and append_file for later chunks" in result.error
    assert not target.exists()


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


def test_workspace_file_tools_include_append_file(tmp_path):
    tools = []
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_bash=False, enable_todo=False, enable_plan=False),
    )

    add_workspace_tools(tools, config, tmp_path)

    assert "append_file" in {tool.name for tool in tools}


def test_sandbox_prompt_limits_single_write_file_content_argument():
    assert (
        f"每次 `write_file(content=...)` / `append_file(content=...)` 控制在 {MAX_FILE_TOOL_CONTENT_CHARS} 字符以内"
        in SANDBOX_INFO_PROMPT
    )
    assert "除非必须用 Python 处理，否则不要把正文塞进 `execute_code`" in SANDBOX_INFO_PROMPT
    assert "用 `write_file` 写第一段，再用 `append_file` 分块续写" in SANDBOX_INFO_PROMPT


def test_system_prompt_warns_against_single_write_file_large_artifacts():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "长 HTML/CSS/JS/JSON/base64/模板正文不要一次性塞进单个工具参数" in prompt
    assert "不要整段塞进 `execute_code`" in prompt
    assert "用 `write_file` 写第一段，再用 `append_file` 分块续写" in prompt
