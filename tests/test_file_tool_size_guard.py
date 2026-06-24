from pathlib import Path

import pytest

from box_agent.tools.file_tools import MAX_FILE_TOOL_CONTENT_CHARS, WriteTool
from box_agent.tools.setup import SANDBOX_INFO_PROMPT


def test_write_file_schema_exposes_content_size_limit():
    content_schema = WriteTool().parameters["properties"]["content"]

    assert content_schema["maxLength"] == MAX_FILE_TOOL_CONTENT_CHARS
    assert f"{MAX_FILE_TOOL_CONTENT_CHARS:,} characters" in content_schema["description"]
    assert "large generated artifacts" in content_schema["description"]
    assert "append smaller chunks" in content_schema["description"]


@pytest.mark.asyncio
async def test_write_file_rejects_oversized_content_before_writing(tmp_path):
    tool = WriteTool(workspace_dir=str(tmp_path))
    target = tmp_path / "output" / "large.html"
    content = "<!doctype html>\n" + ("x" * MAX_FILE_TOOL_CONTENT_CHARS)

    result = await tool.execute(path="output/large.html", content=content)

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith("FILE_TOOL_ARGUMENT_TOO_LARGE")
    assert "Use execute_code to create/truncate the target file" in result.error
    assert not target.exists()


def test_sandbox_prompt_limits_single_write_file_content_argument():
    assert (
        f"每次 `write_file(content=...)` 控制在 {MAX_FILE_TOOL_CONTENT_CHARS} 字符以内"
        in SANDBOX_INFO_PROMPT
    )
    assert "不要把全文塞进一个 `write_file`" in SANDBOX_INFO_PROMPT
    assert "分块 append" in SANDBOX_INFO_PROMPT


def test_system_prompt_warns_against_single_write_file_large_artifacts():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "长 HTML/CSS/JS/JSON/base64/模板正文不要一次性塞进单个 `write_file`" in prompt
    assert "优先用 sandbox 分块创建/追加" in prompt
