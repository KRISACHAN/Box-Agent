from __future__ import annotations

import json
from pathlib import Path

import pytest

from box_agent.tools import mcp_loader
from box_agent.tools.mcp_sources import McpConfigSource, configured_mcp_sources, resolve_mcp_sources


def _write(path: Path, servers: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def test_configured_sources_keep_standalone_single_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BOX_AGENT_USER_MCP_CONFIG_PATH", raising=False)
    monkeypatch.delenv("BOX_AGENT_SYSTEM_MCP_CONFIG_PATH", raising=False)
    monkeypatch.delenv("BOX_AGENT_CONNECTOR_MCP_CONFIG_PATH", raising=False)

    sources = configured_mcp_sources(str(tmp_path / "mcp.json"))

    assert [(source.owner, source.path) for source in sources] == [
        ("user", tmp_path / "mcp.json")
    ]


def test_resolve_sources_preserves_owner_and_blocks_user_shadowing(
    monkeypatch, tmp_path: Path
) -> None:
    system = tmp_path / "mcp.system.json"
    connector = tmp_path / "connector" / "mcp.json"
    user = tmp_path / "mcp.json"
    _write(system, {"playwright": {"command": "pw"}})
    _write(
        connector,
        {
            "law": {
                "url": "https://example.test/mcp",
                "_connectorId": "pkulaw",
                "_connectorName": "北大法宝",
                "credentialRef": "connector:pkulaw:default",
            }
        },
    )
    _write(user, {"playwright": {"command": "shadow"}, "mine": {"command": "mine"}})
    monkeypatch.setenv("BOX_AGENT_USER_MCP_CONFIG_PATH", str(user))
    monkeypatch.setenv("BOX_AGENT_SYSTEM_MCP_CONFIG_PATH", str(system))
    monkeypatch.setenv("BOX_AGENT_CONNECTOR_MCP_CONFIG_PATH", str(connector))

    resolved = resolve_mcp_sources(configured_mcp_sources(str(user)))

    assert resolved.servers["playwright"].owner == "system"
    assert resolved.servers["law"].config_id == "connector:pkulaw"
    assert resolved.servers["law"].connector_id == "pkulaw"
    assert resolved.servers["law"].connector_name == "北大法宝"
    assert resolved.servers["mine"].config_id == "custom-mcp:mine"
    assert resolved.conflicts == ("user:playwright conflicts with system:playwright",)


def test_credential_version_participates_in_server_fingerprint(tmp_path: Path) -> None:
    connector = tmp_path / "mcp.json"
    _write(
        connector,
        {"law": {"url": "https://example.test", "credentialRef": "law-token"}},
    )
    sources = (configured_mcp_sources(str(connector))[0],)

    before = resolve_mcp_sources(sources, {"law-token": 1}).servers["law"]
    after = resolve_mcp_sources(sources, {"law-token": 2}).servers["law"]

    assert before.fingerprint != after.fingerprint


def test_reserved_official_name_is_rejected_even_when_connector_is_disconnected(
    tmp_path: Path,
) -> None:
    user = tmp_path / "mcp.json"
    _write(user, {"pkulaw": {"url": "https://evil.test/mcp"}})

    resolved = resolve_mcp_sources(
        (configured_mcp_sources(str(user))[0],),
        reserved_names={"pkulaw"},
    )

    assert "pkulaw" not in resolved.servers
    assert resolved.conflicts == ("user:pkulaw uses a protected server name",)


def test_connector_source_requires_a_normalized_connector_id(tmp_path: Path) -> None:
    connector = tmp_path / "connector" / "mcp.json"
    _write(connector, {"law": {"url": "https://example.test/mcp", "_connectorId": " PKULAW "}})

    source = McpConfigSource("connector", connector)
    resolved = resolve_mcp_sources((source,))
    assert resolved.servers["law"].connector_id == "pkulaw"

    _write(connector, {"law": {"url": "https://example.test/mcp", "_connectorId": "bad.id"}})
    with pytest.raises(ValueError, match="invalid _connectorId"):
        resolve_mcp_sources((source,))


def test_runtime_connector_source_override_does_not_require_a_physical_file(
    tmp_path: Path,
) -> None:
    user = tmp_path / "mcp.json"
    _write(user, {"mine": {"command": "mine"}})
    connector = McpConfigSource("connector", Path("<runtime:connector>"))

    resolved = resolve_mcp_sources(
        (connector, McpConfigSource("user", user)),
        source_server_overrides={
            "connector": {
                "law": {
                    "url": "https://example.test/mcp",
                    "_connectorId": "pkulaw",
                    "_connectorName": "北大法宝",
                }
            }
        },
    )

    assert resolved.servers["law"].owner == "connector"
    assert resolved.servers["law"].source_path == "<runtime:connector>"
    assert resolved.servers["mine"].owner == "user"


def test_loader_registers_runtime_connector_source_without_connector_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = tmp_path / "mcp.json"
    _write(user, {"mine": {"command": "mine"}})
    monkeypatch.setenv("BOX_AGENT_USER_MCP_CONFIG_PATH", str(user))
    monkeypatch.delenv("BOX_AGENT_SYSTEM_MCP_CONFIG_PATH", raising=False)
    monkeypatch.delenv("BOX_AGENT_CONNECTOR_MCP_CONFIG_PATH", raising=False)
    monkeypatch.delenv("BOX_AGENT_RESERVED_MCP_SERVER_NAMES", raising=False)
    monkeypatch.setattr(
        mcp_loader,
        "_mcp_source_overrides",
        {
            "connector": {
                "law": {
                    "url": "https://example.test/mcp",
                    "_connectorId": "pkulaw",
                }
            }
        },
    )

    resolved = mcp_loader._resolve_registered_sources(str(user))

    assert resolved["law"].owner == "connector"
    assert resolved["law"].source_path == "<runtime:connector>"
    assert resolved["mine"].owner == "user"


@pytest.mark.asyncio
async def test_replace_runtime_connector_source_reconciles_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_loader, "_mcp_source_overrides", {})
    captured: list[str | None] = []

    async def reconcile(source: str | None) -> dict:
        captured.append(source)
        return {"success": True, "source": source, "results": []}

    monkeypatch.setattr(mcp_loader, "_reconcile_mcp_sources_locked", reconcile)

    result = await mcp_loader.replace_mcp_source(
        "connector",
        {
            "mcpServers": {
                "law": {
                    "url": "https://example.test/mcp",
                    "_connectorId": "pkulaw",
                }
            }
        },
    )

    assert result["success"] is True
    assert captured == ["connector"]
    assert set(mcp_loader._mcp_source_overrides["connector"]) == {"law"}


@pytest.fixture
def isolated_connector_runtime(monkeypatch, tmp_path):
    import asyncio

    user = tmp_path / "mcp.json"
    _write(user, {})
    monkeypatch.setenv("BOX_AGENT_USER_MCP_CONFIG_PATH", str(user))
    monkeypatch.delenv("BOX_AGENT_SYSTEM_MCP_CONFIG_PATH", raising=False)
    monkeypatch.delenv("BOX_AGENT_CONNECTOR_MCP_CONFIG_PATH", raising=False)
    monkeypatch.setattr(mcp_loader, "_mcp_config_path", str(user))
    for name in ("_mcp_server_definitions", "_mcp_source_overrides", "_mcp_runtime_credentials",
                 "_mcp_runtime_credential_versions", "_mcp_status", "_mcp_reconnect_locks"):
        monkeypatch.setattr(mcp_loader, name, {})
    monkeypatch.setattr(mcp_loader, "_mcp_connections", [])
    monkeypatch.setattr(mcp_loader, "_mcp_loading", False)
    monkeypatch.setattr(mcp_loader, "_mcp_source_reconcile_lock", asyncio.Lock())
    return {
        "mcpServers": {
            "law": {"url": "https://law.test/mcp", "_connectorId": "pkulaw", "credentialRef": "law-token"},
            "oauth": {"url": "https://oauth.test/mcp", "_connectorId": "qixin"},
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["connector", "system", "user"])
@pytest.mark.parametrize("retry_succeeds", [True, False])
async def test_unchanged_source_retries_failed_servers_without_restarting_healthy_servers(
    monkeypatch, tmp_path, isolated_connector_runtime, source, retry_succeeds,
):
    attempts = {"retry-server": 0, "healthy-server": 0}
    config = {
        "mcpServers": {
            "retry-server": {"url": "https://retry.test/mcp", "_connectorId": "qixin"},
            "healthy-server": {"url": "https://healthy.test/mcp", "_connectorId": "pkulaw"},
        },
    }

    async def connect(connection):
        attempts[connection.name] += 1
        return connection.name == "healthy-server" or (
            retry_succeeds and attempts[connection.name] > 1
        )

    monkeypatch.setattr(mcp_loader.MCPServerConnection, "connect", connect)
    if source == "system":
        system_path = tmp_path / "mcp.system.json"
        _write(system_path, config["mcpServers"])
        monkeypatch.setenv("BOX_AGENT_SYSTEM_MCP_CONFIG_PATH", str(system_path))
    elif source == "user":
        _write(Path(mcp_loader._mcp_config_path), config["mcpServers"])

    async def reconcile():
        if source == "connector":
            return await mcp_loader.replace_mcp_source(source, config)
        return await mcp_loader.reconcile_mcp_sources(source)

    first = await reconcile()
    assert first["success"] is False
    assert attempts == {"retry-server": 1, "healthy-server": 1}

    second = await reconcile()
    assert attempts == {"retry-server": 2, "healthy-server": 1}
    assert second["success"] is retry_succeeds
    assert mcp_loader._mcp_status["retry-server"].state == (
        "connected" if retry_succeeds else "failed"
    )
    if retry_succeeds:
        assert (await reconcile())["success"] is True
        assert attempts == {"retry-server": 2, "healthy-server": 1}


@pytest.mark.asyncio
async def test_late_credential_is_not_acknowledged_by_another_server_reconnect(
    monkeypatch, isolated_connector_runtime,
):
    attempts = []

    async def connect(name):
        attempts.append(name)
        if name == "law" and attempts.count("law") == 1:
            # Credential arrives while the original connection is failing.
            mcp_loader.set_mcp_runtime_credential("law-token", {"Authorization": "Bearer test"})
            return {"success": False}
        return {"success": True}

    monkeypatch.setattr(mcp_loader, "_reconnect_mcp_server_locked", connect)
    await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime)
    await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime)
    assert attempts == ["law", "oauth", "law"]


@pytest.mark.asyncio
async def test_scoped_oauth_update_does_not_publish_or_reconnect_other_connectors(
    monkeypatch, isolated_connector_runtime,
):
    attempts = []

    async def connect(name):
        attempts.append(name)
        return {"success": True}

    monkeypatch.setattr(mcp_loader, "_reconnect_mcp_server_locked", connect)
    await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime, ["qixin"])
    assert attempts == ["oauth"]
    assert set(mcp_loader._mcp_source_overrides["connector"]) == {"oauth"}
    await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime, ["pkulaw"])
    assert attempts == ["oauth", "law"]
    assert set(mcp_loader._mcp_source_overrides["connector"]) == {"oauth", "law"}
    await mcp_loader.replace_mcp_source("connector", {"mcpServers": {}}, ["pkulaw"])
    assert set(mcp_loader._mcp_source_overrides["connector"]) == {"oauth"}


@pytest.mark.asyncio
async def test_missing_credential_waits_without_sending_an_unauthenticated_request(
    monkeypatch, isolated_connector_runtime,
):
    from unittest.mock import AsyncMock, Mock

    build_connection = mcp_loader._build_connection
    build = Mock(side_effect=AssertionError("must not create a transport without credentials"))
    monkeypatch.setattr(mcp_loader, "_build_connection", build)
    result = await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime, ["pkulaw"])
    assert result["results"][0]["waitingForCredential"] is True
    assert not build.called
    assert mcp_loader.get_mcp_status()[0]["state"] == "connecting"

    # The same source must become connectable when its credential arrives.
    monkeypatch.setattr(mcp_loader, "_build_connection", build_connection)
    connect = AsyncMock(return_value=True)
    monkeypatch.setattr(mcp_loader.MCPServerConnection, "connect", connect)
    mcp_loader.set_mcp_runtime_credential("law-token", {"Authorization": "Bearer saved"})
    result = await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime, ["pkulaw"])
    assert result["success"] is True
    connect.assert_awaited_once()
    assert mcp_loader.get_mcp_status()[0]["state"] == "connected"


@pytest.mark.asyncio
async def test_scoped_source_rejects_invalid_connector_filter(isolated_connector_runtime):
    result = await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime, [])
    assert result["success"] is False
    assert mcp_loader._mcp_source_overrides == {}


@pytest.mark.asyncio
async def test_slow_connector_does_not_delay_starting_other_ready_connectors(
    monkeypatch, isolated_connector_runtime,
):
    import asyncio

    other_started = asyncio.Event()

    async def connect(name):
        if name == "law":
            await asyncio.wait_for(other_started.wait(), timeout=1)
        else:
            other_started.set()
        return {"success": True}

    monkeypatch.setattr(mcp_loader, "_reconnect_mcp_server_locked", connect)
    result = await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_cold_load_waits_for_required_credentials_before_creating_transport(
    monkeypatch, isolated_connector_runtime,
):
    from unittest.mock import Mock

    monkeypatch.setattr(mcp_loader, "_mcp_source_overrides", {
        "connector": {"law": isolated_connector_runtime["mcpServers"]["law"]},
    })
    build = Mock(side_effect=AssertionError("unauthenticated transport must not be created"))
    monkeypatch.setattr(mcp_loader, "_build_connection", build)
    assert await mcp_loader.load_mcp_tools_async(mcp_loader._mcp_config_path) == []
    assert not build.called
    assert mcp_loader.get_mcp_status()[0]["error"] == "Waiting for host credential"


@pytest.mark.asyncio
async def test_scoped_replacement_uses_normalized_connector_identity(
    monkeypatch, isolated_connector_runtime,
):
    from unittest.mock import AsyncMock

    connect = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(mcp_loader, "_reconnect_mcp_server_locked", connect)
    isolated_connector_runtime["mcpServers"]["law"]["_connectorId"] = " PKULAW "
    result = await mcp_loader.replace_mcp_source(
        "connector", isolated_connector_runtime, [" PKULAW "],
    )
    assert result["success"] is True
    connect.assert_awaited_once_with("law")
    await mcp_loader.replace_mcp_source("connector", {"mcpServers": {}}, ["pkulaw"])
    assert mcp_loader._mcp_source_overrides["connector"] == {}


@pytest.mark.asyncio
async def test_connector_update_does_not_acknowledge_or_apply_pending_user_source_changes(
    monkeypatch, isolated_connector_runtime,
):
    from unittest.mock import AsyncMock

    user_path = Path(mcp_loader._mcp_config_path)
    _write(user_path, {"mine": {"command": "before"}})
    monkeypatch.setattr(
        mcp_loader, "_mcp_server_definitions",
        mcp_loader._resolve_registered_sources(str(user_path)),
    )
    _write(user_path, {"mine": {"command": "after"}})
    connect = AsyncMock(return_value={"success": True})
    monkeypatch.setattr(mcp_loader, "_reconnect_mcp_server_locked", connect)
    await mcp_loader.replace_mcp_source("connector", isolated_connector_runtime, ["qixin"])
    connect.assert_awaited_once_with("oauth")
    assert mcp_loader._mcp_server_definitions["mine"].config["command"] == "before"
    await mcp_loader.reconcile_mcp_sources("user")
    assert connect.await_args_list[-1].args == ("mine",)
    assert mcp_loader._mcp_server_definitions["mine"].config["command"] == "after"
