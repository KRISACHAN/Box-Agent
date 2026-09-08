"""Host-neutral MCP registry reconciliation helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
from typing import Any

from box_agent.tools.setup import sync_mcp_tool_list, sync_mcp_tools


def sync_mcp_registries(
    mcp_tools: list[Any],
    *,
    base_tools: list[Any],
    base_fallback_tools: MutableMapping[str, Any],
    session_registries: Iterable[
        tuple[MutableMapping[str, Any], MutableMapping[str, Any]]
    ],
    base_sync: Callable[..., Any] = sync_mcp_tool_list,
    session_sync: Callable[..., Any] = sync_mcp_tools,
) -> None:
    """Reconcile one MCP catalog into base and per-session registries.

    Registry containers are supplied by the host adapter; this helper only
    applies the existing provenance-aware ``sync_mcp_*`` operations in a
    consistent order.  Deferred loading and host notifications remain outside
    this function.
    """

    base_sync(base_tools, mcp_tools, base_fallback_tools)
    for tool_map, fallback_tools in session_registries:
        session_sync(tool_map, mcp_tools, fallback_tools)


@dataclass(slots=True)
class MCPRuntimeController:
    """Own the host-neutral target set for MCP registry reconciliation.

    The controller deliberately knows nothing about readiness scheduling,
    authentication, or host notifications.  Adapters choose when to call
    :meth:`reconcile`; this object only supplies the current session targets
    and applies the existing atomic registry operations.
    """

    base_tools: list[Any]
    base_fallback_tools: MutableMapping[str, Any]
    session_registries: Callable[
        [], Iterable[tuple[MutableMapping[str, Any], MutableMapping[str, Any]]]
    ]
    base_sync: Callable[..., Any] = sync_mcp_tool_list
    session_sync: Callable[..., Any] = sync_mcp_tools

    def reconcile(self, mcp_tools: list[Any]) -> None:
        sync_mcp_registries(
            mcp_tools,
            base_tools=self.base_tools,
            base_fallback_tools=self.base_fallback_tools,
            session_registries=self.session_registries(),
            base_sync=self.base_sync,
            session_sync=self.session_sync,
        )


__all__ = ["MCPRuntimeController", "sync_mcp_registries"]
