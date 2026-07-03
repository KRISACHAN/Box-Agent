from __future__ import annotations

from box_agent.cache_fingerprint import build_cache_fingerprint, sha256_fingerprint
from box_agent.schema import Message
from box_agent.tools.base import Tool, ToolResult


class DemoTool(Tool):
    def __init__(
        self,
        name: str,
        *,
        description: str = "Demo tool",
        parameters: dict | None = None,
        server_name: str = "",
    ) -> None:
        self._name = name
        self._description = description
        self._parameters = parameters or {
            "type": "object",
            "properties": {"text": {"type": "string"}},
        }
        self._server_name = server_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, text: str = "") -> ToolResult:
        return ToolResult(success=True, content=text)


def test_sha256_fingerprint_is_stable_for_mapping_order() -> None:
    first = {"b": 2, "a": {"y": 2, "x": 1}}
    second = {"a": {"x": 1, "y": 2}, "b": 2}

    assert sha256_fingerprint(first) == sha256_fingerprint(second)


def test_build_cache_fingerprint_tracks_prompt_tools_skills_and_mcp() -> None:
    messages = [
        Message(role="system", content="system prompt"),
        Message(role="user", content="make a deck"),
    ]
    tools = [
        DemoTool("echo"),
        DemoTool("browser_click", server_name="browser"),
    ]

    fingerprint = build_cache_fingerprint(
        messages=messages,
        tools=tools,
        context={
            "filtered_skill_names": ("beautiful-html-templates", "pptx"),
            "preloaded_skill_names": ["beautiful-html-templates", "pptx"],
        },
    )

    assert fingerprint["system_prompt_hash"].startswith("sha256:")
    assert fingerprint["tool_schema_hash"].startswith("sha256:")
    assert fingerprint["mcp_tool_schema_hash"].startswith("sha256:")
    assert fingerprint["system_prompt_chars"] == len("system prompt")
    assert fingerprint["tool_names"] == ["echo", "browser_click"]
    assert fingerprint["mcp_tool_names"] == ["browser.browser_click"]
    assert fingerprint["filtered_skill_names"] == ["beautiful-html-templates", "pptx"]
    assert fingerprint["preloaded_skill_names"] == ["beautiful-html-templates", "pptx"]


def test_mcp_schema_hash_changes_only_for_mcp_schema_changes() -> None:
    base = [
        DemoTool("echo", description="v1"),
        DemoTool("browser_click", description="click", server_name="browser"),
    ]
    non_mcp_changed = [
        DemoTool("echo", description="v2"),
        DemoTool("browser_click", description="click", server_name="browser"),
    ]
    mcp_changed = [
        DemoTool("echo", description="v1"),
        DemoTool("browser_click", description="click harder", server_name="browser"),
    ]

    base_fp = build_cache_fingerprint(messages=[], tools=base)
    non_mcp_fp = build_cache_fingerprint(messages=[], tools=non_mcp_changed)
    mcp_fp = build_cache_fingerprint(messages=[], tools=mcp_changed)

    assert base_fp["tool_schema_hash"] != non_mcp_fp["tool_schema_hash"]
    assert base_fp["mcp_tool_schema_hash"] == non_mcp_fp["mcp_tool_schema_hash"]
    assert base_fp["mcp_tool_schema_hash"] != mcp_fp["mcp_tool_schema_hash"]
