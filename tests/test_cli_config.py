from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

import box_agent.cli as cli
from box_agent.workspace_registry import WorkspaceRegistry


def _write_config(path: Path, api_key: str = "sk-test-key") -> None:
    path.write_text(
        "\n".join(
            [
                f'api_key: "{api_key}"',
                'api_base: "https://api.openai.com/v1"',
                'model: "gpt-4o"',
                'provider: "openai"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_cmd_config_get_reads_expanded_config_defaults(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: config_path)

    exit_code = cli.cmd_config(get_key="llm.max_output_tokens")

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "63999"


def test_cmd_config_set_bootstraps_and_updates_raw_yaml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, api_key="YOUR_API_KEY_HERE")
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: None)
    monkeypatch.setattr(cli.Config, "_ensure_user_config", lambda: config_path)

    exit_code = cli.cmd_config(set_pair=("api_key", "sk-new-key"))

    assert exit_code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["api_key"] == "sk-new-key"


def test_cmd_config_set_rolls_back_invalid_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    original = config_path.read_text(encoding="utf-8")
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: config_path)

    exit_code = cli.cmd_config(set_pair=("context_window", "not-an-int"))

    assert exit_code == 1
    assert config_path.read_text(encoding="utf-8") == original


def test_cmd_config_json_masks_secret_values(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, api_key="sk-secret-token")
    monkeypatch.setattr(cli.Config, "find_config_file", lambda _name: config_path)

    exit_code = cli.cmd_config(json_output=True)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["llm"]["api_key"] == "sk-s****oken"


def test_config_parses_goal_autopilot_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    with config_path.open("a", encoding="utf-8") as f:
        f.write("goal_autopilot_enabled: false\n")
        f.write("goal_autopilot_max_turns: 5\n")
        f.write("goal_autopilot_max_seconds: 120\n")
        f.write("goal_autopilot_no_progress_turns: 4\n")

    config = cli.Config.from_yaml(config_path)

    assert config.agent.goal_autopilot_enabled is False
    assert config.agent.goal_autopilot_max_turns == 5
    assert config.agent.goal_autopilot_max_seconds == 120
    assert config.agent.goal_autopilot_no_progress_turns == 4


def test_config_sub_agent_token_limit_defaults_and_overrides(tmp_path: Path) -> None:
    # Default when absent from yaml.
    default_path = tmp_path / "default.yaml"
    _write_config(default_path)
    assert cli.Config.from_yaml(default_path).agent.sub_agent_token_limit == 40_000

    # Overridable for advanced/host scenarios even though it is not surfaced
    # in config-example.yaml.
    override_path = tmp_path / "override.yaml"
    _write_config(override_path)
    with override_path.open("a", encoding="utf-8") as f:
        f.write("sub_agent_token_limit: 12345\n")

    assert cli.Config.from_yaml(override_path).agent.sub_agent_token_limit == 12345


def test_config_batch_synthesis_timeout_defaults_and_overrides(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    _write_config(default_path)
    assert (
        cli.Config.from_yaml(default_path).agent.sub_agent_batch_synthesis_timeout_seconds
        == 300.0
    )

    override_path = tmp_path / "override.yaml"
    _write_config(override_path)
    with override_path.open("a", encoding="utf-8") as f:
        f.write("sub_agent_batch_synthesis_timeout_seconds: 123.5\n")

    assert (
        cli.Config.from_yaml(override_path).agent.sub_agent_batch_synthesis_timeout_seconds
        == 123.5
    )


def test_config_mcp_connect_timeout_defaults_and_overrides(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    _write_config(default_path)
    assert cli.Config.from_yaml(default_path).tools.mcp.connect_timeout == 60.0

    override_path = tmp_path / "override.yaml"
    _write_config(override_path)
    with override_path.open("a", encoding="utf-8") as f:
        f.write("tools:\n")
        f.write("  mcp:\n")
        f.write("    connect_timeout: 15\n")
    assert cli.Config.from_yaml(override_path).tools.mcp.connect_timeout == 15.0


def test_config_parallel_tool_timeout_defaults_and_overrides(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    _write_config(default_path)
    assert cli.Config.from_yaml(default_path).agent.parallel_tool_timeout_seconds == 900.0

    override_path = tmp_path / "override.yaml"
    _write_config(override_path)
    with override_path.open("a", encoding="utf-8") as f:
        f.write("parallel_tool_timeout_seconds: 12.5\n")

    assert cli.Config.from_yaml(override_path).agent.parallel_tool_timeout_seconds == 12.5

    disabled_path = tmp_path / "disabled.yaml"
    _write_config(disabled_path)
    with disabled_path.open("a", encoding="utf-8") as f:
        f.write("parallel_tool_timeout_seconds: 0\n")

    assert cli.Config.from_yaml(disabled_path).agent.parallel_tool_timeout_seconds == 0


def test_context_resource_dedup_defaults_on_and_can_be_disabled(tmp_path: Path) -> None:
    default_path = tmp_path / "default.yaml"
    _write_config(default_path)
    assert cli.Config.from_yaml(default_path).agent.context_resource_dedup_enabled is True

    disabled_path = tmp_path / "disabled.yaml"
    _write_config(disabled_path)
    with disabled_path.open("a", encoding="utf-8") as stream:
        stream.write("context_resource_dedup_enabled: false\n")

    assert cli.Config.from_yaml(disabled_path).agent.context_resource_dedup_enabled is False


def test_cmd_doctor_json_returns_structured_status(monkeypatch, capsys) -> None:
    async def fake_api_status(_config):
        return cli._doctor_check("ok", "api ok")

    monkeypatch.setattr(cli, "_doctor_config_status", lambda: (cli._doctor_check("ok", "config ok"), object()))
    monkeypatch.setattr(cli, "_doctor_api_status", fake_api_status)
    monkeypatch.setattr(cli, "_doctor_sandbox_status", lambda: cli._doctor_check("ok", "sandbox ok"))
    monkeypatch.setattr(cli, "_doctor_mcp_status", lambda: cli._doctor_check("warning", "mcp missing"))
    monkeypatch.setattr(cli, "_doctor_browser_status", lambda: cli._doctor_check("warning", "browser missing"))
    monkeypatch.setattr(cli, "_doctor_obsidian_status", lambda: cli._doctor_check("warning", "obsidian missing"))

    exit_code = asyncio.run(cli.cmd_doctor(json_output=True))

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["checks"]["api"]["message"] == "api ok"


def test_cmd_doctor_json_returns_nonzero_on_error(monkeypatch, capsys) -> None:
    async def fake_api_status(_config):
        return cli._doctor_check("skipped", "no config")

    monkeypatch.setattr(cli, "_doctor_config_status", lambda: (cli._doctor_check("error", "missing"), None))
    monkeypatch.setattr(cli, "_doctor_api_status", fake_api_status)
    monkeypatch.setattr(cli, "_doctor_sandbox_status", lambda: cli._doctor_check("ok", "sandbox ok"))
    monkeypatch.setattr(cli, "_doctor_mcp_status", lambda: cli._doctor_check("warning", "mcp missing"))
    monkeypatch.setattr(cli, "_doctor_browser_status", lambda: cli._doctor_check("warning", "browser missing"))
    monkeypatch.setattr(cli, "_doctor_obsidian_status", lambda: cli._doctor_check("warning", "obsidian missing"))

    exit_code = asyncio.run(cli.cmd_doctor(json_output=True))

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["checks"]["config"]["status"] == "error"


def test_main_returns_run_agent_exit_code(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    async def fake_run_agent(*args, **kwargs):
        assert args[0] == tmp_path
        assert kwargs["task"] == "do work"
        assert kwargs["verify_api"] is False
        assert kwargs["json_summary"] is True
        assert kwargs["deep_think"] is True
        assert kwargs["force_plan_start"] is True
        assert kwargs["completion_gate_enabled"] is False
        assert kwargs["goal_autopilot_enabled"] is False
        assert kwargs["initial_goal"] == "ship goal"
        return 7

    monkeypatch.setattr(cli, "parse_args", lambda: argparse.Namespace(
        command=None,
        workspace=str(tmp_path),
        task="do work",
        goal="ship goal",
        json=True,
        no_verify_api=True,
        deep_think=True,
        force_plan_start=True,
        no_completion_gate=True,
        no_goal_autopilot=True,
        no_sandbox=False,
    ))
    monkeypatch.setattr(cli.Config, "_ensure_user_config", lambda: config_path)
    monkeypatch.setattr(
        cli.Config,
        "from_yaml",
        lambda _path: SimpleNamespace(llm=SimpleNamespace(api_key="sk-test-key")),
    )
    monkeypatch.setattr(cli, "run_agent", fake_run_agent)

    assert cli.main() == 7


def test_main_persists_code_workspace_type_without_creating_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    workspace = tmp_path / "project"
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    async def fake_run_agent(*args, **kwargs):
        return 0

    monkeypatch.setattr(
        cli,
        "parse_args",
        lambda: argparse.Namespace(
            command=None,
            workspace=str(workspace),
            workspace_type="code",
            task="inspect code",
            goal=None,
            json=False,
            no_verify_api=True,
            deep_think=False,
            force_plan_start=False,
            no_completion_gate=True,
            no_goal_autopilot=True,
            no_sandbox=False,
        ),
    )
    monkeypatch.setattr(cli.Config, "_ensure_user_config", lambda: config_path)
    monkeypatch.setattr(
        cli.Config,
        "from_yaml",
        lambda _path: SimpleNamespace(llm=SimpleNamespace(api_key="sk-test-key")),
    )
    monkeypatch.setattr(cli, "run_agent", fake_run_agent)

    assert cli.main() == 0
    assert WorkspaceRegistry().get(workspace).task_type == "code"
    assert not (workspace / "output").exists()


def test_cmd_goal_persists_workspace_goal(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert cli.cmd_goal(workspace, action="set", text=["Ship", "goal"], json_output=True) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["goal"]["objective"] == "Ship goal"
    assert first["goal"]["status"] == "active"

    assert cli.cmd_goal(
        workspace,
        action="complete",
        evidence=["uv run pytest tests/ -q passed"],
        json_output=True,
    ) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["goal"]["status"] == "complete"
    assert second["goal"]["evidence"] == ["uv run pytest tests/ -q passed"]
    assert second["goal"]["completedBy"] == "cli"

    stored = cli._load_goal_state(workspace)
    assert stored is not None
    assert stored.status == "complete"
    assert stored.evidence == ["uv run pytest tests/ -q passed"]
