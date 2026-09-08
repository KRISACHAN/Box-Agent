from __future__ import annotations

import json
from pathlib import Path

import pytest

from box_agent.tools.mcp_bootstrap import (
    HOSTED_SEARCH_URL_ENV,
    HOSTED_SEARCH_SERVER_NAME,
    MANAGED_MCP_SCHEMA_KEY,
    bootstrap_managed_mcp_config,
)


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    entry = runtime / "bin" / "box-agent-acp"
    entry.parent.mkdir(parents=True)
    entry.write_text("runtime", encoding="utf-8")
    (runtime / "manifest.json").write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "box-agent-web-extract": {
                        "entry": "bin/box-agent-acp",
                        "args": ["--web-extract-mcp"],
                        "transport": "stdio",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return runtime


def test_bootstrap_adds_hosted_search_and_runtime_server(tmp_path: Path) -> None:
    config = tmp_path / "home" / "mcp.json"
    runtime = _runtime(tmp_path)

    result = bootstrap_managed_mcp_config(config, runtime_root=runtime)

    assert result.changed is True
    payload = json.loads(config.read_text(encoding="utf-8"))
    assert payload[MANAGED_MCP_SCHEMA_KEY] == 1
    assert payload["mcpServers"][HOSTED_SEARCH_SERVER_NAME]["disabled"] is False
    extract = payload["mcpServers"]["box-agent-web-extract"]
    assert extract["command"] == str(runtime / "bin" / "box-agent-acp")
    assert extract["args"] == ["--web-extract-mcp"]
    assert extract["disabled"] is False


def test_bootstrap_migrates_legacy_disabled_defaults_once(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    HOSTED_SEARCH_SERVER_NAME: {
                        "url": "https://xiaohuanxiong.com/api/web/mcp/web_search/v1/mcp",
                        "type": "streamable_http",
                        "disabled": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    bootstrap_managed_mcp_config(config)
    payload = json.loads(config.read_text(encoding="utf-8"))

    assert payload["mcpServers"][HOSTED_SEARCH_SERVER_NAME]["disabled"] is False


def test_bootstrap_adds_installed_web_extract_for_cli(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    command = tmp_path / "bin" / "box-agent-web-extract-mcp"
    command.parent.mkdir()
    command.write_text("cli", encoding="utf-8")

    bootstrap_managed_mcp_config(
        config,
        web_extract_command=str(command),
    )
    payload = json.loads(config.read_text(encoding="utf-8"))

    extract = payload["mcpServers"]["box-agent-web-extract"]
    assert extract["command"] == str(command)
    assert extract["args"] == []
    assert extract["disabled"] is False


def test_bootstrap_preserves_user_disable_and_existing_url_after_migration(
    tmp_path: Path,
) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                MANAGED_MCP_SCHEMA_KEY: 1,
                "mcpServers": {
                    HOSTED_SEARCH_SERVER_NAME: {
                        "url": "https://old.example/mcp",
                        "disabled": True,
                    },
                    "custom": {"command": "custom-mcp", "disabled": False},
                },
            }
        ),
        encoding="utf-8",
    )

    bootstrap_managed_mcp_config(config)
    payload = json.loads(config.read_text(encoding="utf-8"))

    search = payload["mcpServers"][HOSTED_SEARCH_SERVER_NAME]
    assert search["url"] == "https://old.example/mcp"
    assert search["disabled"] is True
    assert payload["mcpServers"]["custom"] == {
        "command": "custom-mcp",
        "disabled": False,
    }


def test_bootstrap_preserves_host_environment_url_on_first_migration(
    tmp_path: Path,
) -> None:
    config = tmp_path / "mcp.json"
    environment_url = (
        "https://code-test.xiaohuanxiong.com/api/web/mcp/web_search/v1/mcp"
    )
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    HOSTED_SEARCH_SERVER_NAME: {
                        "url": environment_url,
                        "type": "streamable_http",
                        "disabled": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    bootstrap_managed_mcp_config(config)
    payload = json.loads(config.read_text(encoding="utf-8"))
    search = payload["mcpServers"][HOSTED_SEARCH_SERVER_NAME]

    assert search["url"] == environment_url
    assert search["disabled"] is False


def test_bootstrap_applies_host_url_override_to_official_managed_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                MANAGED_MCP_SCHEMA_KEY: 1,
                "mcpServers": {
                    HOSTED_SEARCH_SERVER_NAME: {
                        "url": "https://xiaohuanxiong.com/api/web/mcp/web_search/v1/mcp",
                        "disabled": True,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        HOSTED_SEARCH_URL_ENV,
        "https://code-test.xiaohuanxiong.com/api/web/mcp/web_search/v1/mcp",
    )

    bootstrap_managed_mcp_config(config)
    search = json.loads(config.read_text(encoding="utf-8"))["mcpServers"][
        HOSTED_SEARCH_SERVER_NAME
    ]

    assert search["url"] == (
        "https://code-test.xiaohuanxiong.com/api/web/mcp/web_search/v1/mcp"
    )
    assert search["disabled"] is True


def test_bootstrap_host_override_does_not_replace_custom_search_provider(
    tmp_path: Path,
) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                MANAGED_MCP_SCHEMA_KEY: 1,
                "mcpServers": {
                    HOSTED_SEARCH_SERVER_NAME: {
                        "url": "https://mcp.example.com/custom-search",
                        "disabled": False,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    bootstrap_managed_mcp_config(
        config,
        hosted_search_url=(
            "https://code-test.xiaohuanxiong.com/api/web/mcp/web_search/v1/mcp"
        ),
    )
    search = json.loads(config.read_text(encoding="utf-8"))["mcpServers"][
        HOSTED_SEARCH_SERVER_NAME
    ]

    assert search["url"] == "https://mcp.example.com/custom-search"


def test_bootstrap_rejects_invalid_host_url_without_writing(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"

    result = bootstrap_managed_mcp_config(
        config,
        hosted_search_url="file:///etc/passwd",
    )

    assert result.changed is False
    assert result.warning is not None
    assert config.exists() is False


def test_bootstrap_is_idempotent(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"

    first = bootstrap_managed_mcp_config(config)
    second = bootstrap_managed_mcp_config(config)

    assert first.changed is True
    assert second.changed is False


def test_bootstrap_does_not_overwrite_malformed_config(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text("not-json", encoding="utf-8")

    result = bootstrap_managed_mcp_config(config)

    assert result.changed is False
    assert result.warning is not None
    assert config.read_text(encoding="utf-8") == "not-json"


def test_bootstrap_rejects_runtime_entry_outside_root(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "manifest.json").write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "unsafe": {
                        "entry": "../outside",
                        "args": [],
                        "transport": "stdio",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    bootstrap_managed_mcp_config(config, runtime_root=runtime)
    payload = json.loads(config.read_text(encoding="utf-8"))

    assert "unsafe" not in payload["mcpServers"]


@pytest.mark.parametrize("bundled", [False, True])
def test_managed_stdio_uses_current_profile_and_preserves_other_server_env(
    tmp_path, monkeypatch, bundled,
):
    root = tmp_path / "profile"
    root.mkdir()
    monkeypatch.setenv("BOX_AGENT_HOME", str(root))
    config = root / "mcp.json"
    custom = {"command": "custom-mcp", "env": {"CUSTOM": "kept"}}
    config.write_text(json.dumps({"mcpServers": {
        "box-agent-web-extract": {"env": {
            "BOX_AGENT_HOME": str(tmp_path / "old-profile"), "CUSTOM": "kept",
        }},
        "custom": custom,
    }}), encoding="utf-8")
    kwargs = {"runtime_root": _runtime(tmp_path)} if bundled else {
        "web_extract_command": "fixture-web-extract",
    }
    bootstrap_managed_mcp_config(config, **kwargs)
    servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["box-agent-web-extract"]["env"] == {
        "BOX_AGENT_HOME": str(root.resolve()), "CUSTOM": "kept",
    }
    assert servers["custom"] == custom
    assert "env" not in servers[HOSTED_SEARCH_SERVER_NAME]
    assert not bootstrap_managed_mcp_config(config, **kwargs).changed


def test_unset_profile_preserves_managed_server_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("BOX_AGENT_HOME", raising=False)
    config = tmp_path / "mcp.json"
    existing_env = {"CUSTOM": "kept"}
    config.write_text(json.dumps({"mcpServers": {
        "box-agent-web-extract": {"env": existing_env},
    }}), encoding="utf-8")
    bootstrap_managed_mcp_config(config, web_extract_command="fixture-web-extract")
    servers = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["box-agent-web-extract"]["env"] == existing_env


@pytest.mark.asyncio
@pytest.mark.parametrize("has_config", [True, False])
async def test_managed_web_extract_child_loads_only_profile_config(
    tmp_path, monkeypatch, has_config,
):
    import sys
    from box_agent.tools.mcp_loader import MCPServerConnection

    root = tmp_path / "profile"
    (root / "config").mkdir(parents=True)
    monkeypatch.setenv("BOX_AGENT_HOME", str(root))
    if has_config:
        (root / "config/config.yaml").write_text(
            "api_key: fixture-key\napi_base: https://example.invalid/v1\n"
            "provider: openai\nmodel: profile-fixture\n",
            encoding="utf-8",
        )
    child = tmp_path / "web_extract_fixture.py"
    child.write_text('''
import json, os, sys
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from box_agent.mcp_servers import web_extract_server as server
from box_agent.tools.base import ToolResult

original_create_llm = server._create_configured_llm
def checked_create_llm():
    # Fail before config lookup if propagation regresses; never read real user data.
    assert os.environ.get("BOX_AGENT_HOME") == sys.argv[2], "Missing child profile"
    return original_create_llm()
server._create_configured_llm = checked_create_llm
server.LLMClient = lambda **kwargs: SimpleNamespace(**kwargs)
def fake_extractor(llm):
    async def execute(**kwargs):
        return ToolResult(success=True, content=json.dumps({
            "model": llm.model, "auth_file": llm.auth_file,
        }))
    return SimpleNamespace(execute=execute)
server.WebExtractTool = fake_extractor
server.main()
''', encoding="utf-8")
    config = root / "config/mcp.json"
    bootstrap_managed_mcp_config(config, web_extract_command=sys.executable)
    entry = json.loads(config.read_text(encoding="utf-8"))["mcpServers"]["box-agent-web-extract"]
    connection = MCPServerConnection(
        name="box-agent-web-extract", command=entry["command"],
        args=[str(child), str(Path(__file__).resolve().parents[1]), str(root.resolve())],
        env=entry.get("env"), connect_timeout=15, execute_timeout=15,
    )
    try:
        assert await connection.connect()
        result = await connection.session.call_tool(
            "web_extract", {"url": "https://example.invalid/fixture"},
        )
        if has_config:
            assert not result.isError, result.content
            assert json.loads(result.content[0].text) == {
                "model": "profile-fixture", "auth_file": str(root.resolve() / "config/auth.json"),
            }
        else:
            assert result.isError
            assert "Explicit profile config.yaml is missing" in result.content[0].text
    finally:
        await connection.disconnect()
