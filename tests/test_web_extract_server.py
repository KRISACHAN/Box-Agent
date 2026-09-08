from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jsonschema import Draft202012Validator
from mcp.server.fastmcp.exceptions import ToolError

from box_agent.llm import AnthropicClient, OpenAIClient
from box_agent.mcp_servers import web_extract_server
from box_agent.tools.base import ToolResult
from box_agent.tools.mcp_loader import MCPTool


@pytest.mark.asyncio
async def test_advertised_parameters_have_explicit_types_in_both_provider_formats():
    listed = await web_extract_server.mcp.list_tools()
    assert len(listed) == 1
    tool = listed[0]
    assert tool.name == "web_extract"
    wrapper = MCPTool(
        name=tool.name,
        description=tool.description or "",
        parameters=tool.inputSchema,
        session=SimpleNamespace(),
    )
    openai = OpenAIClient._convert_tools(None, [wrapper])[0]
    anthropic = AnthropicClient._convert_tools(None, [wrapper])[0]

    for schema in (
        tool.inputSchema,
        openai["function"]["parameters"],
        anthropic["input_schema"],
    ):
        Draft202012Validator.check_schema(schema)
        assert schema["required"] == ["url"]
        for name, expected_type in (
            ("url", "string"),
            ("model", "string"),
            ("max_output_tokens", "integer"),
        ):
            parameter = schema["properties"][name]
            assert parameter["type"] == expected_type
            assert "anyOf" not in parameter
            assert "default" not in parameter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "optional_arguments",
    [{}, {"model": "summary-model", "max_output_tokens": 8_000}],
)
async def test_advertised_tool_accepts_omitted_or_typed_optional_arguments(
    optional_arguments,
):
    tool = (await web_extract_server.mcp.list_tools())[0]
    session = SimpleNamespace(
        call_tool=AsyncMock(
            return_value=SimpleNamespace(content=[], isError=False),
        ),
    )
    wrapper = MCPTool(
        name=tool.name,
        description=tool.description or "",
        parameters=tool.inputSchema,
        session=session,
    )
    arguments = {"url": "https://example.com", **optional_arguments}
    result = await wrapper.invoke(arguments)
    assert result.success
    session.call_tool.assert_awaited_once_with("web_extract", arguments=arguments)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"url": "https://example.com", "model": 12},
        {"url": "https://example.com", "max_output_tokens": "invalid"},
        {"url": "https://example.com", "max_output_tokens": 0},
        {"url": "https://example.com", "model": None},
        {"url": "https://example.com", "max_output_tokens": None},
        {"url": "https://example.com", "unknown": True},
    ],
)
async def test_advertised_tool_rejects_invalid_arguments_before_dispatch(arguments):
    tool = (await web_extract_server.mcp.list_tools())[0]
    session = SimpleNamespace(call_tool=AsyncMock())
    wrapper = MCPTool(
        name=tool.name,
        description=tool.description or "",
        parameters=tool.inputSchema,
        session=session,
    )
    result = await wrapper.invoke(arguments)
    assert not result.success
    assert result.error.startswith("INVALID_TOOL_ARGUMENTS:")
    session.call_tool.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "optional_arguments",
    [
        {},
        {"model": "summary-model", "max_output_tokens": 8_000},
        {"model": None, "max_output_tokens": None},
    ],
)
async def test_mcp_execution_preserves_defaults_values_and_legacy_nulls(
    monkeypatch, optional_arguments,
):
    extractor = SimpleNamespace(
        execute=AsyncMock(return_value=ToolResult(success=True, content="extracted")),
    )
    monkeypatch.setattr(web_extract_server, "_extractor", lambda: extractor)
    content, structured = await web_extract_server.mcp.call_tool(
        "web_extract", {"url": "https://example.com", **optional_arguments},
    )
    assert content[0].text == "extracted"
    assert structured == {"result": "extracted"}
    extractor.execute.assert_awaited_once_with(
        url="https://example.com",
        model=optional_arguments.get("model"),
        max_output_tokens=optional_arguments.get("max_output_tokens"),
    )


@pytest.mark.asyncio
async def test_mcp_execution_reports_extraction_failure(monkeypatch):
    extractor = SimpleNamespace(
        execute=AsyncMock(
            return_value=ToolResult(success=False, error="Web extraction timed out"),
        ),
    )
    monkeypatch.setattr(web_extract_server, "_extractor", lambda: extractor)
    with pytest.raises(ToolError, match="Web extraction timed out"):
        await web_extract_server.mcp.call_tool(
            "web_extract", {"url": "https://example.com"},
        )
