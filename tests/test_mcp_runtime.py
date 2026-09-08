from __future__ import annotations

from box_agent.mcp_runtime import MCPRuntimeController, sync_mcp_registries


class _Tool:
    def __init__(self, name: str, *, mcp_tool_id: str | None = None) -> None:
        self.name = name
        self.mcp_tool_id = mcp_tool_id


def test_sync_mcp_registries_updates_base_and_session_targets() -> None:
    base_tools: list[_Tool] = []
    base_fallback_tools: dict[str, _Tool] = {}
    session_tools: dict[str, _Tool] = {}
    session_fallback_tools: dict[str, _Tool] = {}
    remote = _Tool("mcp__demo__search", mcp_tool_id="remote-1")

    sync_mcp_registries(
        [remote],
        base_tools=base_tools,
        base_fallback_tools=base_fallback_tools,
        session_registries=[(session_tools, session_fallback_tools)],
    )

    assert base_tools == [remote]
    assert session_tools == {remote.name: remote}
    assert base_fallback_tools == {}
    assert session_fallback_tools == {}


def test_sync_mcp_registries_preserves_stable_overrides_in_fallbacks() -> None:
    stable = _Tool("mcp__demo__search")
    old_remote = _Tool("mcp__demo__search", mcp_tool_id="old")
    remote = _Tool("mcp__demo__search", mcp_tool_id="new")
    base_tools = [stable]
    base_fallback_tools: dict[str, _Tool] = {}
    session_tools = {stable.name: stable}
    session_fallback_tools: dict[str, _Tool] = {}

    sync_mcp_registries(
        [old_remote],
        base_tools=base_tools,
        base_fallback_tools=base_fallback_tools,
        session_registries=[(session_tools, session_fallback_tools)],
    )
    sync_mcp_registries(
        [remote],
        base_tools=base_tools,
        base_fallback_tools=base_fallback_tools,
        session_registries=[(session_tools, session_fallback_tools)],
    )

    assert base_tools == [remote]
    assert session_tools == {remote.name: remote}
    assert base_fallback_tools == {stable.name: stable}
    assert session_fallback_tools == {stable.name: stable}


def test_mcp_runtime_controller_reads_current_session_targets_each_reconcile() -> None:
    base_tools: list[_Tool] = []
    base_fallback_tools: dict[str, _Tool] = {}
    session_tools: dict[str, _Tool] = {}
    session_fallback_tools: dict[str, _Tool] = {}
    controller = MCPRuntimeController(
        base_tools=base_tools,
        base_fallback_tools=base_fallback_tools,
        session_registries=lambda: [(session_tools, session_fallback_tools)],
    )

    first = _Tool("mcp__demo__first", mcp_tool_id="first")
    second_tools: dict[str, _Tool] = {}
    second_fallback_tools: dict[str, _Tool] = {}
    controller.reconcile([first])
    assert session_tools == {first.name: first}

    # The provider is evaluated for each call, so a newly-created session is
    # reconciled without rebuilding the controller.
    session_tools = second_tools
    session_fallback_tools = second_fallback_tools
    second = _Tool("mcp__demo__second", mcp_tool_id="second")
    controller.reconcile([second])
    assert second_tools == {second.name: second}
    assert session_tools == second_tools


def test_sync_mcp_registries_accepts_legacy_operation_hooks() -> None:
    calls: list[tuple[str, int]] = []

    def base_sync(base, tools, fallback):
        calls.append(("base", len(tools)))

    def session_sync(tool_map, tools, fallback):
        calls.append(("session", len(tools)))

    sync_mcp_registries(
        [_Tool("mcp__demo__search", mcp_tool_id="remote")],
        base_tools=[],
        base_fallback_tools={},
        session_registries=[({}, {})],
        base_sync=base_sync,
        session_sync=session_sync,
    )

    assert calls == [("base", 1), ("session", 1)]
