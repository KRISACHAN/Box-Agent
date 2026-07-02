"""MCP configuration tool — add/remove/enable/disable/list MCP servers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from box_agent.config import Config
from box_agent.tools.base import Tool, ToolResult


def _resolve_write_target() -> Path:
    # Priority: loader's actual runtime path > user config dir > packaged config.
    # In dev, box-agent may boot before ~/.box-agent/config/mcp.json exists and
    # end up loading ./box_agent/config/mcp.json. Writing to user dir here would
    # split the two views: loader keeps reading dev copy, watcher sees the user
    # copy, reconnects come up empty. Following the loader's resolved path keeps
    # tool + loader + host watcher pointed at the same file.
    try:
        from box_agent.tools.mcp_loader import get_mcp_config_path
        loader_path = get_mcp_config_path()
        if loader_path:
            p = Path(loader_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
    except Exception:
        pass

    user_path = Path("~/.box-agent/config/mcp.json").expanduser()
    if user_path.exists():
        return user_path
    try:
        p = Config.find_config_file("mcp.json")
        if p and p.exists():
            return p
    except Exception:
        pass
    user_path.parent.mkdir(parents=True, exist_ok=True)
    return user_path


class McpConfigTool(Tool):
    """Manage MCP server entries in mcp.json."""

    @property
    def name(self) -> str:
        return "mcp_config"

    @property
    def description(self) -> str:
        return (
            "Read or modify the MCP server configuration (mcp.json). "
            "Actions: list — show current servers; "
            "add — add or replace a server entry; "
            "remove — delete a server entry; "
            "enable / disable — toggle a server without deleting it. "
            "This tool only writes the file; the host watches mcp.json and "
            "applies hot reload automatically (or after box-agent restart)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "add", "remove", "enable", "disable"],
                    "description": "Operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Server name key in mcpServers (required for add/remove/enable/disable).",
                },
                "config": {
                    "type": "object",
                    "description": (
                        "Server config object for 'add'. "
                        "For stdio: {command, args?, env?}. "
                        "For URL-based: {url, type?: 'sse'|'http'|'streamable_http', headers?}. "
                        "Optional: connect_timeout, execute_timeout, sse_read_timeout, disabled."
                    ),
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, name: str = "", config: dict | None = None) -> ToolResult:
        target = _resolve_write_target()

        if target.exists():
            try:
                with open(target, encoding="utf-8") as f:
                    data: dict[str, Any] = json.load(f)
            except Exception as e:
                return ToolResult(success=False, content="", error=f"Failed to read {target}: {e}")
        else:
            data = {"mcpServers": {}}

        servers: dict[str, Any] = data.setdefault("mcpServers", {})

        if action == "list":
            if not servers:
                return ToolResult(success=True, content=f"No MCP servers configured in {target}")
            lines = [f"MCP config: {target}", ""]
            for sname, scfg in servers.items():
                disabled = scfg.get("disabled", False)
                status = "disabled" if disabled else "enabled"
                conn = scfg.get("url") or scfg.get("command") or "?"
                lines.append(f"  {sname} [{status}]  {conn}")
            return ToolResult(success=True, content="\n".join(lines))

        if not name:
            return ToolResult(success=False, content="", error="'name' is required for this action")

        if action == "remove":
            if name not in servers:
                return ToolResult(success=False, content="", error=f"Server '{name}' not found")
            del servers[name]

        elif action in ("enable", "disable"):
            if name not in servers:
                return ToolResult(success=False, content="", error=f"Server '{name}' not found")
            servers[name]["disabled"] = (action == "disable")

        elif action == "add":
            if config is None:
                return ToolResult(success=False, content="", error="'config' object is required for add")
            # Only fields that mcp_loader actually consumes are kept; legacy
            # lazy / keywords are silently dropped because the runtime never
            # honored them.
            _ALLOWED = {
                "command", "args", "env", "url", "type", "transport", "headers",
                "connect_timeout", "execute_timeout", "sse_read_timeout",
                "disabled",
            }
            entry = {k: v for k, v in config.items() if k in _ALLOWED}
            servers[name] = entry

        else:
            return ToolResult(success=False, content="", error=f"Unknown action: {action}")

        try:
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                f.write("\n")
        except Exception as e:
            return ToolResult(success=False, content="", error=f"Failed to write {target}: {e}")

        return ToolResult(
            success=True,
            content=(
                f"Done. {target} updated. "
                "Host watches this file and applies hot reload automatically; "
                "if no host is driving reconnects, restart box-agent to load."
            ),
        )
