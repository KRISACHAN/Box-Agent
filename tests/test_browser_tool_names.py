from types import SimpleNamespace

import pytest

from box_agent.tools.browser_tool_names import (
    browser_tool_fixed_arguments,
    is_browser_tool_name,
    public_browser_tool_description,
    public_browser_tool_name,
    public_browser_tool_parameters,
    public_browser_tool_text,
)
from box_agent.tools.mcp_loader import MCPTool


def test_playwright_tools_use_managed_browser_namespace():
    assert (
        public_browser_tool_name("playwright", "browser_navigate")
        == "managed_browser_navigate"
    )


def test_gateway_tools_use_user_browser_namespace():
    assert (
        public_browser_tool_name("browser-gateway", "browser_read_current_page")
        == "user_browser_read_current_page"
    )
    assert (
        public_browser_tool_name("browser-gateway", "browser_connector_click")
        == "user_browser_click"
    )
    assert (
        public_browser_tool_name("browser-gateway", "browser_connector_custom")
        == "user_browser_custom"
    )
    assert (
        public_browser_tool_name("browser-gateway", "browser_custom")
        == "user_browser_custom"
    )


def test_unknown_gateway_names_use_user_namespace_in_model_facing_text():
    rewritten = public_browser_tool_text(
        "browser-gateway",
        "Try browser_connector_custom, browser_session_custom, or browser_custom.",
    )

    assert rewritten == (
        "Try user_browser_custom, user_browser_session_custom, or "
        "user_browser_custom."
    )


def test_gateway_description_uses_public_tool_names():
    description = (
        "Call browser_connector_snapshot before browser_connector_click and "
        "never mix refs with browser_navigate."
    )
    rewritten = public_browser_tool_description("browser-gateway", description)

    assert "user_browser_snapshot" in rewritten
    assert "user_browser_click" in rewritten
    assert "managed_browser_navigate" in rewritten
    assert rewritten.startswith("User browser controlled through browser-gateway.")
    assert "browser_connector_" not in rewritten


def test_playwright_description_names_managed_browser_controller():
    rewritten = public_browser_tool_description(
        "playwright",
        "Navigate to a URL.",
    )

    assert rewritten == (
        "Managed browser controlled through Playwright MCP. Navigate to a URL."
    )

    named = public_browser_tool_description(
        "playwright",
        "Call browser_navigate before browser_snapshot.",
    )
    assert "managed_browser_navigate" in named
    assert "managed_browser_snapshot" in named


def test_browser_result_text_hides_transport_tool_names():
    rewritten = public_browser_tool_text(
        "browser-gateway",
        "Try browser_connector_snapshot, then browser_connector_click; "
        "use browser_read_page to refresh.",
    )

    assert "user_browser_snapshot" in rewritten
    assert "user_browser_click" in rewritten
    assert "user_browser_read_page" in rewritten
    assert "browser_connector_" not in rewritten


def test_only_new_public_browser_names_are_recognized():
    assert is_browser_tool_name("managed_browser_snapshot") is True
    assert is_browser_tool_name("user_browser_submit") is True
    assert is_browser_tool_name("browser_snapshot") is False
    assert is_browser_tool_name("managed_browser.snapshot") is False


def test_user_browser_schema_hides_and_fixes_source_preference():
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "source_preference": {"type": "string"},
        },
        "required": ["url", "source_preference"],
    }

    fixed = browser_tool_fixed_arguments("browser-gateway", parameters)
    public_parameters = public_browser_tool_parameters(parameters, fixed)

    assert fixed == {"source_preference": "browser_connector"}
    assert "source_preference" not in public_parameters["properties"]
    assert public_parameters["required"] == ["url"]
    assert "source_preference" in parameters["properties"]


@pytest.mark.asyncio
async def test_public_wrapper_calls_original_mcp_transport_name():
    class FakeSession:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return SimpleNamespace(content=[], isError=False)

    session = FakeSession()
    tool = MCPTool(
        name="managed_browser_navigate",
        remote_name="browser_navigate",
        description="Navigate",
        parameters={"type": "object"},
        session=session,
        server_name="test-playwright",
    )

    result = await tool.execute(url="https://example.com")

    assert result.success is True
    assert session.calls == [("browser_navigate", {"url": "https://example.com"})]


@pytest.mark.asyncio
async def test_public_wrapper_preserves_transport_like_text_in_success_results():
    class FakeSession:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(
                content=[SimpleNamespace(text="The page documents browser_navigate")],
                isError=False,
            )

    tool = MCPTool(
        name="user_browser_click",
        remote_name="browser_connector_click",
        description="Click",
        parameters={"type": "object"},
        session=FakeSession(),
        server_name="browser-gateway",
    )

    result = await tool.execute(ref="button-1")

    assert result.success is True
    assert result.content == "The page documents browser_navigate"


@pytest.mark.asyncio
async def test_public_wrapper_rewrites_transport_names_in_error_results():
    class FakeSession:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(
                content=[SimpleNamespace(text="Try browser_connector_snapshot first")],
                isError=True,
            )

    tool = MCPTool(
        name="user_browser_click",
        remote_name="browser_connector_click",
        description="Click",
        parameters={"type": "object"},
        session=FakeSession(),
        server_name="browser-gateway",
    )

    result = await tool.execute(ref="button-1")

    assert result.success is False
    assert result.content == "Try user_browser_snapshot first"
    assert result.error == "Try user_browser_snapshot first"


@pytest.mark.asyncio
async def test_public_wrapper_rewrites_transport_names_in_exceptions():
    class FakeSession:
        async def call_tool(self, name, arguments):
            raise RuntimeError(f"Unknown tool: {name}")

    tool = MCPTool(
        name="user_browser_click",
        remote_name="browser_connector_click",
        description="Click",
        parameters={"type": "object"},
        session=FakeSession(),
        server_name="browser-gateway",
    )

    result = await tool.execute(ref="button-1")

    assert result.success is False
    assert result.error == "MCP tool execution failed: Unknown tool: user_browser_click"


@pytest.mark.asyncio
async def test_fixed_browser_source_cannot_be_overridden_by_model_arguments():
    class FakeSession:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return SimpleNamespace(content=[], isError=False)

    session = FakeSession()
    tool = MCPTool(
        name="user_browser_read_page",
        remote_name="browser_read_page",
        description="Read from the user's browser",
        parameters={"type": "object"},
        session=session,
        server_name="browser-gateway",
        fixed_arguments={"source_preference": "browser_connector"},
    )

    result = await tool.execute(
        url="https://example.com",
        source_preference="playwright",
    )

    assert result.success is True
    assert session.calls == [
        (
            "browser_read_page",
            {
                "url": "https://example.com",
                "source_preference": "browser_connector",
            },
        )
    ]
