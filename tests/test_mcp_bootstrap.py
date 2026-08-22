from __future__ import annotations

import json
from pathlib import Path

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
