"""Session-scoped MCP discovery and deferred tool exposure."""

from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass

from .base import Tool, ToolResult
from .mcp_tool_catalog import MCPToolCatalog

TOOL_SEARCH_NAME = "tool_search"


@dataclass(frozen=True, slots=True)
class ActivatedMCPTool:
    tool_id: str
    model_name: str
    generation: int


@dataclass(frozen=True, slots=True)
class ToolExposure:
    tools: list[Tool]
    offered_names: frozenset[str]
    mcp_generations: dict[str, int]


class ToolSearchTool(Tool):
    """Search the MCP catalog and activate usable hits for this session."""

    reserved_deferred_mcp_search = True

    def __init__(
        self,
        catalog: MCPToolCatalog,
        activated: OrderedDict[str, ActivatedMCPTool],
    ) -> None:
        self._catalog = catalog
        self._activated = activated

    @property
    def name(self) -> str:
        return TOOL_SEARCH_NAME

    @property
    def description(self) -> str:
        return (
            "Search connected MCP tools by capability. Matching tools become "
            "available for direct calls on the next model step."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Capability, action, or tool name to search for.",
                },
                "server_name": {
                    "type": "string",
                    "description": "Optional exact MCP server name filter.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        query: str,
        server_name: str | None = None,
        top_k: int = 3,
    ) -> ToolResult:
        hits = self._catalog.search(query, server_name=server_name, top_k=top_k)
        activated_results = []
        conflicts = []
        for entry in hits:
            if entry.name_conflict or entry.model_name == TOOL_SEARCH_NAME:
                conflicts.append(
                    {
                        "tool_id": entry.tool_id,
                        "name": entry.model_name,
                        "server_name": entry.server_name,
                        "error": (
                            "reserved deferred-search tool name"
                            if entry.model_name == TOOL_SEARCH_NAME
                            else "duplicate model-facing tool name"
                        ),
                    }
                )
                continue
            previous = self._activated.get(entry.tool_id)
            already_active = (
                previous is not None and previous.generation == entry.generation
            )
            self._activated[entry.tool_id] = ActivatedMCPTool(
                tool_id=entry.tool_id,
                model_name=entry.model_name,
                generation=entry.generation,
            )
            activated_results.append(
                {
                    "name": entry.model_name,
                    "server_name": entry.server_name,
                    "description": entry.description,
                    "already_active": already_active,
                }
            )
        payload = {
            "success": not conflicts or bool(activated_results),
            "query": query,
            "activated": activated_results,
            "conflicts": conflicts,
            "notice": (
                "Activated tools are callable by their real name on the next step."
                if activated_results
                else (
                    "Matching tools have conflicting model-facing names."
                    if conflicts
                    else "No matching MCP tools found."
                )
            ),
        }
        conflict_error = None
        if conflicts and not activated_results:
            conflict_error = (
                "MCP tool name conflict; adjust MCP configuration before activation."
            )
        return ToolResult(
            success=conflict_error is None,
            content=json.dumps(payload, ensure_ascii=False),
            error=conflict_error,
        )


class MCPToolExposureManager:
    """Build one step's visible tool set from a session activation store."""

    def __init__(
        self,
        catalog: MCPToolCatalog,
        activated: OrderedDict[str, ActivatedMCPTool],
    ) -> None:
        self._catalog = catalog
        self._activated = activated

    def prepare_tools(self, candidates: list[Tool]) -> ToolExposure:
        visible: list[Tool] = []
        generations: dict[str, int] = {}
        for tool in candidates:
            tool_id = getattr(tool, "mcp_tool_id", None)
            if tool_id is None:
                visible.append(tool)
                continue
            entry = self._catalog.get(tool_id)
            if entry is None or entry.name_conflict:
                continue
            activation = self._activated.get(tool_id)
            activated = activation is not None and activation.generation == entry.generation
            if not entry.always_load and not activated:
                continue
            visible.append(entry.tool)
            generations[entry.model_name] = entry.generation
        names = frozenset(tool.name for tool in visible)
        return ToolExposure(visible, names, generations)

    def inherited_tools(self, tool_map: dict[str, Tool]) -> dict[str, Tool]:
        """Give child agents only the parent's currently visible real tools."""
        exposure = self.prepare_tools(list(tool_map.values()))
        return {
            tool.name: tool
            for tool in exposure.tools
            if tool.name != TOOL_SEARCH_NAME
        }

    def validate_call(
        self,
        name: str,
        offered_generation: int | None,
        target_tool: Tool | None = None,
    ) -> str | None:
        if offered_generation is None:
            return None
        current = self._catalog.get_by_model_name(name)
        if current is None:
            return f"MCP tool '{name}' is unavailable or has a name conflict; search again."
        if current.generation != offered_generation:
            return f"MCP tool '{name}' changed after it was offered; search again."
        if (
            target_tool is not None
            and getattr(target_tool, "mcp_generation", None) != offered_generation
        ):
            return f"MCP tool '{name}' execution target changed after it was offered; search again."
        return None
