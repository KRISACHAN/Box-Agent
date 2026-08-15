"""Process-wide catalog of tools discovered from connected MCP servers.

The catalog owns discovery metadata only.  Which catalog entries are visible to
an LLM is decided per Agent session by :mod:`mcp_tool_search`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from threading import RLock

from .base import Tool


def _normalize(value: str) -> str:
    value = value.strip().lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value)


@dataclass(frozen=True, slots=True)
class MCPToolEntry:
    tool_id: str
    model_name: str
    server_name: str
    raw_tool_name: str
    description: str
    tool: Tool
    generation: int
    always_load: bool
    name_conflict: bool = False


class MCPToolCatalog:
    """Thread-safe current snapshot of connected MCP tools."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._entries: dict[str, MCPToolEntry] = {}
        self._server_generations: dict[str, int] = {}

    def replace_server(self, server_name: str, tools: Iterable[Tool]) -> int:
        """Replace one server snapshot and return its new generation."""
        with self._lock:
            generation = self._server_generations.get(server_name, 0) + 1
            self._server_generations[server_name] = generation
            self._entries = {
                tool_id: entry
                for tool_id, entry in self._entries.items()
                if entry.server_name != server_name
            }
            for tool in tools:
                raw_name = tool.name
                tool_id = f"mcp:{server_name}/{raw_name}"
                # MCPTool exposes these attributes.  Keeping the catalog
                # tolerant of Tool doubles makes focused tests inexpensive.
                tool._mcp_generation = generation
                self._entries[tool_id] = MCPToolEntry(
                    tool_id=tool_id,
                    model_name=raw_name,
                    server_name=server_name,
                    raw_tool_name=raw_name,
                    description=tool.description,
                    tool=tool,
                    generation=generation,
                    always_load=bool(getattr(tool, "mcp_always_load", False)),
                )
            self._rebuild_conflicts()
            return generation

    def remove_server(self, server_name: str) -> None:
        with self._lock:
            self._entries = {
                tool_id: entry
                for tool_id, entry in self._entries.items()
                if entry.server_name != server_name
            }
            self._rebuild_conflicts()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._server_generations.clear()

    def snapshot(self) -> tuple[MCPToolEntry, ...]:
        with self._lock:
            return tuple(sorted(self._entries.values(), key=lambda entry: entry.tool_id))

    def get(self, tool_id: str) -> MCPToolEntry | None:
        with self._lock:
            return self._entries.get(tool_id)

    def get_by_model_name(self, model_name: str) -> MCPToolEntry | None:
        matches = [entry for entry in self.snapshot() if entry.model_name == model_name]
        if len(matches) != 1 or matches[0].name_conflict:
            return None
        return matches[0]

    def search(
        self,
        query: str,
        *,
        server_name: str | None = None,
        top_k: int = 5,
    ) -> list[MCPToolEntry]:
        normalized_query = _normalize(query)
        if not normalized_query:
            return []
        ranked: list[tuple[int, str, MCPToolEntry]] = []
        for entry in self.snapshot():
            if server_name and entry.server_name != server_name:
                continue
            normalized_name = _normalize(entry.model_name)
            normalized_id = _normalize(entry.tool_id)
            normalized_server_name = _normalize(
                f"{entry.server_name} {entry.model_name}"
            )
            normalized_desc = _normalize(entry.description)
            if normalized_query == normalized_name:
                score = 0
            elif normalized_query == normalized_id:
                score = 1
            elif normalized_query in normalized_server_name:
                score = 2
            elif normalized_query in normalized_name:
                score = 3
            elif normalized_query in normalized_desc:
                score = 4
            else:
                words = normalized_query.split()
                haystack = f"{normalized_server_name} {normalized_desc} {normalized_id}"
                if not all(word in haystack for word in words):
                    continue
                score = 5
            ranked.append((score, entry.tool_id, entry))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [entry for _, _, entry in ranked[: max(1, top_k)]]

    def _rebuild_conflicts(self) -> None:
        counts: dict[str, int] = {}
        for entry in self._entries.values():
            counts[entry.model_name] = counts.get(entry.model_name, 0) + 1
        self._entries = {
            tool_id: MCPToolEntry(
                tool_id=entry.tool_id,
                model_name=entry.model_name,
                server_name=entry.server_name,
                raw_tool_name=entry.raw_tool_name,
                description=entry.description,
                tool=entry.tool,
                generation=entry.generation,
                always_load=entry.always_load,
                name_conflict=counts[entry.model_name] > 1,
            )
            for tool_id, entry in self._entries.items()
        }


_CATALOG = MCPToolCatalog()


def get_mcp_tool_catalog() -> MCPToolCatalog:
    return _CATALOG
