"""MCP tool loader with real MCP client integration and timeout handling."""

import asyncio
import json
import sys
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx


# Python 3.10 compatibility: asyncio.timeout was added in 3.11
if sys.version_info >= (3, 11):
    _timeout = asyncio.timeout
else:

    @asynccontextmanager
    async def _timeout(delay: float):  # type: ignore[misc]
        """Minimal asyncio.timeout shim for Python 3.10."""
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()
        handle = loop.call_later(delay, task.cancel)  # type: ignore[union-attr]
        try:
            yield
        except asyncio.CancelledError:
            raise TimeoutError(f"Timed out after {delay}s")
        finally:
            handle.cancel()

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from box_agent.auth import request_auth_headers, resolve_auth_token, should_attach_auth_header

from .base import Tool, ToolResult


def _warn(msg: str) -> None:
    """Write diagnostic message to stderr (never stdout)."""
    sys.stderr.write(msg + "\n")

# Connection type aliases
ConnectionType = Literal["stdio", "sse", "http", "streamable_http"]


@dataclass
class MCPTimeoutConfig:
    """MCP timeout configuration."""

    connect_timeout: float = 10.0  # Connection timeout (seconds)
    execute_timeout: float = 60.0  # Tool execution timeout (seconds)
    sse_read_timeout: float = 120.0  # SSE read timeout (seconds)


# Global default timeout config
_default_timeout_config = MCPTimeoutConfig()


class DynamicBearerAuth(httpx.Auth):
    """Attach the latest hosted login token to every HTTP request.

    URL-based MCP transports keep a persistent HTTP client alive across tool
    calls. Reading auth.json in this auth hook keeps MCP behavior aligned with
    LLM clients, which refresh login auth before each API request.
    """

    requires_request_body = False
    requires_response_body = False

    def __init__(self, auth_file: str = "", explicit_token: str = ""):
        self.auth_file = auth_file
        self.explicit_token = explicit_token

    def sync_auth_flow(self, request: httpx.Request):
        yield self._with_current_auth(request)

    async def async_auth_flow(self, request: httpx.Request):
        yield self._with_current_auth(request)

    def _with_current_auth(self, request: httpx.Request) -> httpx.Request:
        if "authorization" in request.headers:
            return request

        token = resolve_auth_token(self.explicit_token, self.auth_file)
        if not token or not should_attach_auth_header(str(request.url)):
            return request

        request.headers["Authorization"] = f"Bearer {token}"
        return request


def _has_authorization_header(headers: dict[str, str] | None) -> bool:
    return any(key.lower() == "authorization" for key in (headers or {}))


def _dynamic_bearer_auth_for_url(
    url: str | None,
    headers: dict[str, str],
    auth_file: str = "",
    auth_token: str = "",
) -> DynamicBearerAuth | None:
    if not url or _has_authorization_header(headers) or not should_attach_auth_header(url):
        return None
    return DynamicBearerAuth(auth_file=auth_file, explicit_token=auth_token)


def set_mcp_timeout_config(
    connect_timeout: float | None = None,
    execute_timeout: float | None = None,
    sse_read_timeout: float | None = None,
) -> None:
    """Set global MCP timeout configuration.

    Args:
        connect_timeout: Connection timeout in seconds
        execute_timeout: Tool execution timeout in seconds
        sse_read_timeout: SSE read timeout in seconds
    """
    global _default_timeout_config
    if connect_timeout is not None:
        _default_timeout_config.connect_timeout = connect_timeout
    if execute_timeout is not None:
        _default_timeout_config.execute_timeout = execute_timeout
    if sse_read_timeout is not None:
        _default_timeout_config.sse_read_timeout = sse_read_timeout


def get_mcp_timeout_config() -> MCPTimeoutConfig:
    """Get current MCP timeout configuration."""
    return _default_timeout_config


class MCPTool(Tool):
    """Wrapper for MCP tools with timeout handling."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        session: ClientSession,
        server_name: str = "",
        execute_timeout: float | None = None,
    ):
        self._name = name
        self._server_name = server_name
        self._description = description
        self._parameters = parameters
        self._session = session
        self._execute_timeout = execute_timeout

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
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs) -> ToolResult:
        """Execute MCP tool via the session with timeout protection."""
        timeout = self._execute_timeout or _default_timeout_config.execute_timeout

        try:
            # Wrap call_tool with timeout
            async with _timeout(timeout):
                result = await self._session.call_tool(self._name, arguments=kwargs)

            # MCP tool results are a list of content items
            content_parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    content_parts.append(item.text)
                else:
                    content_parts.append(str(item))

            content_str = "\n".join(content_parts)

            is_error = result.isError if hasattr(result, "isError") else False

            if is_error:
                err_msg = content_str.strip() or "Tool returned error"
                return ToolResult(success=False, content=content_str, error=err_msg)
            return ToolResult(success=True, content=content_str, error=None)

        except TimeoutError:
            return ToolResult(
                success=False,
                content="",
                error=f"MCP tool execution timed out after {timeout}s. The remote server may be slow or unresponsive.",
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=f"MCP tool execution failed: {str(e)}")


class MCPServerConnection:
    """Manages connection to a single MCP server (STDIO or URL-based) with timeout handling."""

    def __init__(
        self,
        name: str,
        connection_type: ConnectionType = "stdio",
        # STDIO params
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        # URL-based params
        url: str | None = None,
        headers: dict[str, str] | None = None,
        auth: httpx.Auth | None = None,
        # Timeout overrides (per-server)
        connect_timeout: float | None = None,
        execute_timeout: float | None = None,
        sse_read_timeout: float | None = None,
    ):
        self.name = name
        self.connection_type = connection_type
        # STDIO
        self.command = command
        self.args = args or []
        self.env = env or {}
        # URL-based
        self.url = url
        self.headers = headers or {}
        self.auth = auth
        # Timeout settings (per-server overrides)
        self.connect_timeout = connect_timeout
        self.execute_timeout = execute_timeout
        self.sse_read_timeout = sse_read_timeout
        # Connection state
        self.last_error: str | None = None
        self.session: ClientSession | None = None
        self.exit_stack: AsyncExitStack | None = None
        self.tools: list[MCPTool] = []

    def _get_connect_timeout(self) -> float:
        """Get effective connect timeout."""
        return self.connect_timeout or _default_timeout_config.connect_timeout

    def _get_sse_read_timeout(self) -> float:
        """Get effective SSE read timeout."""
        return self.sse_read_timeout or _default_timeout_config.sse_read_timeout

    def _get_execute_timeout(self) -> float:
        """Get effective execute timeout."""
        return self.execute_timeout or _default_timeout_config.execute_timeout

    async def connect(self) -> bool:
        """Connect to the MCP server with timeout protection."""
        connect_timeout = self._get_connect_timeout()

        async def _close_exit_stack() -> None:
            if not self.exit_stack:
                return
            try:
                await self.exit_stack.aclose()
            except BaseException as cleanup_error:  # noqa: BLE001
                _warn(f"⚠ Failed to clean up MCP connection '{self.name}': {cleanup_error}")
            finally:
                self.exit_stack = None

        try:
            self.exit_stack = AsyncExitStack()

            # Wrap connection with timeout
            async with _timeout(connect_timeout):
                if self.connection_type == "stdio":
                    read_stream, write_stream = await self._connect_stdio()
                elif self.connection_type == "sse":
                    read_stream, write_stream = await self._connect_sse()
                else:  # http / streamable_http
                    read_stream, write_stream = await self._connect_streamable_http()

                # Enter client session context
                session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
                self.session = session

                # Initialize the session
                await session.initialize()

                # List available tools
                tools_list = await session.list_tools()

            # Wrap each tool with execute timeout
            execute_timeout = self._get_execute_timeout()
            for tool in tools_list.tools:
                parameters = tool.inputSchema if hasattr(tool, "inputSchema") else {}
                mcp_tool = MCPTool(
                    name=tool.name,
                    description=tool.description or "",
                    parameters=parameters,
                    session=session,
                    server_name=self.name,
                    execute_timeout=execute_timeout,
                )
                self.tools.append(mcp_tool)

            conn_info = self.url if self.url else self.command
            _warn(f"✓ Connected to MCP server '{self.name}' ({self.connection_type}: {conn_info}) - loaded {len(self.tools)} tools")
            for tool in self.tools:
                desc = tool.description[:60] if len(tool.description) > 60 else tool.description
                _warn(f"  - {tool.name}: {desc}...")
            self.last_error = None
            return True

        except TimeoutError:
            self.last_error = f"Connection timed out after {connect_timeout}s"
            _warn(f"✗ Connection to MCP server '{self.name}' timed out after {connect_timeout}s")
            await _close_exit_stack()
            return False

        except asyncio.CancelledError as e:
            self.last_error = f"Connection cancelled: {e}"
            _warn(f"✗ Connection to MCP server '{self.name}' was cancelled during initialization: {e}")
            await _close_exit_stack()
            return False

        except Exception as e:
            self.last_error = str(e)
            _warn(f"✗ Failed to connect to MCP server '{self.name}': {e}")
            await _close_exit_stack()
            import traceback

            traceback.print_exc()
            return False

    async def _connect_stdio(self):
        """Connect via STDIO transport.

        Force a writable cwd (system temp) so child processes (e.g.
        @playwright/mcp) can create working directories without hitting
        permission errors on protected paths like ``C:\\Program Files\\``.
        """
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env if self.env else None,
            cwd=tempfile.gettempdir(),
        )
        return await self.exit_stack.enter_async_context(stdio_client(server_params))

    async def _connect_sse(self):
        """Connect via SSE transport with timeout parameters."""
        connect_timeout = self._get_connect_timeout()
        sse_read_timeout = self._get_sse_read_timeout()

        return await self.exit_stack.enter_async_context(
            sse_client(
                url=self.url,
                headers=self.headers if self.headers else None,
                timeout=connect_timeout,
                sse_read_timeout=sse_read_timeout,
                auth=self.auth,
            )
        )

    async def _connect_streamable_http(self):
        """Connect via Streamable HTTP transport with timeout parameters."""
        connect_timeout = self._get_connect_timeout()
        sse_read_timeout = self._get_sse_read_timeout()

        # streamablehttp_client returns (read, write, get_session_id)
        read_stream, write_stream, _ = await self.exit_stack.enter_async_context(
            streamablehttp_client(
                url=self.url,
                headers=self.headers if self.headers else None,
                timeout=connect_timeout,
                sse_read_timeout=sse_read_timeout,
                auth=self.auth,
            )
        )
        return read_stream, write_stream

    async def disconnect(self):
        """Properly disconnect from the MCP server."""
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except Exception:
                # anyio cancel scope may raise RuntimeError or ExceptionGroup
                # when stdio_client's task group is closed from a different
                # task context during shutdown.
                pass
            finally:
                self.exit_stack = None
                self.session = None


# Global connections registry
_mcp_connections: list[MCPServerConnection] = []


@dataclass
class McpServerStatus:
    name: str
    state: str  # connecting | connected | failed | disabled
    transport: str = ""
    tool_count: int = 0
    tools: list = field(default_factory=list)
    error: str | None = None


_mcp_status: dict[str, McpServerStatus] = {}
_mcp_loading: bool = False
_mcp_config_path: str | None = None


def is_mcp_loading() -> bool:
    return _mcp_loading


def get_mcp_config_path() -> str | None:
    return _mcp_config_path


def get_mcp_tools_for_server(name: str) -> list:
    """Return the Tool objects currently held by a connected server."""
    conn = next((c for c in _mcp_connections if c.name == name), None)
    return list(conn.tools) if conn else []


async def disconnect_mcp_server(name: str) -> dict:
    """Disconnect a named MCP server and return its removed tool names."""
    global _mcp_connections
    conn = next((c for c in _mcp_connections if c.name == name), None)
    removed_tools: list[str] = []
    if conn:
        removed_tools = [t.name for t in conn.tools]
        try:
            await conn.disconnect()
        except Exception:
            pass
        _mcp_connections = [c for c in _mcp_connections if c.name != name]
    _record_status(name, "disabled")
    return {"success": True, "removedTools": removed_tools}


def _record_status(
    name: str,
    state: str,
    transport: str = "",
    tool_count: int = 0,
    tools: list | None = None,
    error: str | None = None,
) -> None:
    _mcp_status[name] = McpServerStatus(
        name=name, state=state, transport=transport,
        tool_count=tool_count, tools=tools or [], error=error,
    )


def get_mcp_status() -> list[dict]:
    return [
        {
            "name": s.name,
            "state": s.state,
            "transport": s.transport,
            "toolCount": s.tool_count,
            "tools": s.tools,
            "error": s.error,
        }
        for s in _mcp_status.values()
    ]


def _determine_connection_type(server_config: dict) -> ConnectionType:
    """Determine connection type from server config."""
    explicit_type = str(server_config.get("type") or server_config.get("transport") or "").lower()
    if explicit_type in ("stdio", "sse", "http", "streamable_http"):
        return explicit_type
    # Auto-detect: if url exists, default to streamable_http; otherwise stdio
    if server_config.get("url"):
        return "streamable_http"
    return "stdio"


def _resolve_mcp_config_path(config_path: str) -> Path | None:
    """
    Resolve MCP config path with fallback logic.

    Priority:
    1. If the specified path exists, use it
    2. If mcp.json doesn't exist, try mcp-example.json in the same directory
    3. Return None if no config found

    Args:
        config_path: User-specified config path

    Returns:
        Resolved Path object or None if not found
    """
    config_file = Path(config_path)

    # If specified path exists, use it directly
    if config_file.exists():
        return config_file

    # Fallback: if looking for mcp.json, try mcp-example.json
    if config_file.name == "mcp.json":
        example_file = config_file.parent / "mcp-example.json"
        if example_file.exists():
            _warn(f"mcp.json not found, using template: {example_file}")
            return example_file

    return None


async def load_mcp_tools_async(
    config_path: str = "mcp.json",
    auth_token: str = "",
    auth_file: str = "",
) -> list[Tool]:
    """
    Load MCP tools from config file.

    This function:
    1. Reads the MCP config file (with fallback to mcp-example.json)
    2. Connects to each server (STDIO or URL-based)
    3. Fetches tool definitions
    4. Wraps them as Tool objects

    Supported config formats:
    - STDIO: {"command": "...", "args": [...], "env": {...}}
    - URL-based: {"url": "https://...", "type": "sse|http|streamable_http", "headers": {...}}

    Per-server timeout overrides (optional):
    - "connect_timeout": float - Connection timeout in seconds
    - "execute_timeout": float - Tool execution timeout in seconds
    - "sse_read_timeout": float - SSE read timeout in seconds

    Note:
    - If mcp.json is not found, will automatically fallback to mcp-example.json
    - User-specific mcp.json should be created by copying mcp-example.json

    Args:
        config_path: Path to MCP configuration file (default: "mcp.json")
        auth_token: Optional in-memory product login token.
        auth_file: Optional auth.json path read before connecting URL-based
            MCP servers that do not define their own Authorization.

    Returns:
        List of Tool objects representing MCP tools
    """
    global _mcp_connections, _mcp_status, _mcp_loading, _mcp_config_path
    _mcp_loading = True

    config_file = _resolve_mcp_config_path(config_path)
    if config_file is not None:
        _mcp_config_path = str(config_file)

    if config_file is None:
        _warn(f"MCP config not found: {config_path}")
        return []

    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        mcp_servers = config.get("mcpServers", {})

        if not mcp_servers:
            import sys as _sys
            _sys.stderr.write("No MCP servers configured\n")
            return []

        connections: list[MCPServerConnection] = []

        # Build connection objects for each enabled server
        for server_name, server_config in mcp_servers.items():
            if server_config.get("disabled", False):
                _warn(f"Skipping disabled server: {server_name}")
                _record_status(server_name, "disabled")
                continue

            conn_type = _determine_connection_type(server_config)
            url = server_config.get("url")
            command = server_config.get("command")

            # Validate config
            if conn_type == "stdio" and not command:
                _warn(f"No command specified for STDIO server: {server_name}")
                continue
            if conn_type in ("sse", "http", "streamable_http") and not url:
                _warn(f"No url specified for {conn_type.upper()} server: {server_name}")
                continue

            configured_headers = server_config.get("headers", {})
            auth = _dynamic_bearer_auth_for_url(
                url=url,
                headers=configured_headers,
                auth_file=auth_file,
                auth_token=auth_token,
            )
            connection_headers = (
                configured_headers
                if auth is not None
                else request_auth_headers(
                    auth_file=auth_file,
                    explicit_token=auth_token,
                    existing=configured_headers,
                    url=url,
                )
            )

            connections.append(
                MCPServerConnection(
                    name=server_name,
                    connection_type=conn_type,
                    command=command,
                    args=server_config.get("args", []),
                    env=server_config.get("env", {}),
                    url=url,
                    headers=connection_headers,
                    auth=auth,
                    # Per-server timeout overrides from mcp.json
                    connect_timeout=server_config.get("connect_timeout"),
                    execute_timeout=server_config.get("execute_timeout"),
                    sse_read_timeout=server_config.get("sse_read_timeout"),
                )
            )

        # Connect to all servers in parallel — one slow/broken server no
        # longer blocks the others. Each connection has its own timeout.

        # Seed connecting state before gather so UI shows spinner during window
        for conn in connections:
            _record_status(conn.name, "connecting", transport=conn.url or conn.command or "")

        results = await asyncio.gather(
            *(conn.connect() for conn in connections),
            return_exceptions=True,
        )

        all_tools = []
        for conn, success in zip(connections, results):
            if isinstance(success, BaseException):
                _warn(f"✗ MCP server '{conn.name}' raised during connect: {success}")
                _record_status(
                    conn.name, "failed",
                    transport=conn.url or conn.command or "",
                    error=str(success),
                )
                continue
            if success:
                _mcp_connections.append(conn)
                all_tools.extend(conn.tools)
                _record_status(
                    conn.name, "connected",
                    transport=conn.url or conn.command or "",
                    tool_count=len(conn.tools),
                    tools=[t.name for t in conn.tools],
                )
            else:
                _record_status(
                    conn.name, "failed",
                    transport=conn.url or conn.command or "",
                    error=conn.last_error or "connect() returned False",
                )

        _warn(f"Total MCP tools loaded: {len(all_tools)}")

        return all_tools

    except Exception as e:
        _warn(f"Error loading MCP config: {e}")
        import traceback

        traceback.print_exc()
        return []

    finally:
        _mcp_loading = False


async def cleanup_mcp_connections():
    """Clean up all MCP connections."""
    global _mcp_connections
    for connection in _mcp_connections:
        await connection.disconnect()
    _mcp_connections.clear()


async def reconnect_mcp_server(name: str) -> dict:
    """Re-read mcp.json and reconnect a single named MCP server in-place."""
    global _mcp_connections

    if not _mcp_config_path:
        return {"success": False, "error": "mcp.json path unknown; box-agent not yet initialized"}

    try:
        with open(_mcp_config_path, encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        return {"success": False, "error": f"Cannot read {_mcp_config_path}: {e}", "configPath": _mcp_config_path}

    server_config = config.get("mcpServers", {}).get(name)
    if not server_config:
        return {"success": False, "error": f"Server '{name}' not found in mcp.json", "configPath": _mcp_config_path}

    if server_config.get("disabled"):
        _record_status(name, "disabled")
        return {"success": False, "error": "Server is disabled", "configPath": _mcp_config_path}

    # Drop any existing connection for this server.
    old_conn = next((c for c in _mcp_connections if c.name == name), None)
    if old_conn:
        try:
            await old_conn.disconnect()
        except Exception:
            pass
        _mcp_connections = [c for c in _mcp_connections if c.name != name]

    conn_type = _determine_connection_type(server_config)
    url = server_config.get("url")
    command = server_config.get("command")
    transport_label = url or command or ""

    conn = MCPServerConnection(
        name=name,
        connection_type=conn_type,
        command=command,
        args=server_config.get("args", []),
        env=server_config.get("env", {}),
        url=url,
        headers=server_config.get("headers", {}),
        connect_timeout=server_config.get("connect_timeout"),
        execute_timeout=server_config.get("execute_timeout"),
        sse_read_timeout=server_config.get("sse_read_timeout"),
    )

    _record_status(name, "connecting", transport=transport_label)
    try:
        success = await conn.connect()
    except Exception as e:
        _record_status(name, "failed", transport=transport_label, error=str(e))
        return {"success": False, "error": str(e), "configPath": _mcp_config_path}

    if success:
        _mcp_connections.append(conn)
        _record_status(
            name, "connected",
            transport=transport_label,
            tool_count=len(conn.tools),
            tools=[t.name for t in conn.tools],
        )
        return {"success": True, "toolCount": len(conn.tools), "tools": [t.name for t in conn.tools], "configPath": _mcp_config_path}

    _record_status(name, "failed", transport=transport_label, error=conn.last_error)
    return {"success": False, "error": conn.last_error or "connect() returned False", "configPath": _mcp_config_path}
