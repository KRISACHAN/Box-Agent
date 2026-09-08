"""Regression coverage for the Windows-specific runtime builder."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from scripts import build_runtime, build_win_runtime


def test_windows_builder_uses_shared_pyinstaller_contract() -> None:
    hidden = build_win_runtime._windows_pyinstaller_hidden_imports()
    collect = build_win_runtime._windows_pyinstaller_collect_args()

    assert hidden == build_runtime.pyinstaller_hidden_imports(
        external_python_sandbox=True
    )
    assert collect == build_runtime.pyinstaller_collect_args(
        external_python_sandbox=True
    )
    assert "box_agent.mcp_servers" in hidden
    assert "box_agent.mcp_servers.web_extract" in hidden
    assert "box_agent.mcp_servers.web_extract_server" in hidden
    assert "PIL.Image" in hidden
    assert "ipykernel" not in hidden
    assert "sklearn" not in collect


def test_windows_legacy_bundle_remains_explicitly_available() -> None:
    assert build_win_runtime._windows_pyinstaller_hidden_imports(
        external_python_sandbox=False
    ) == build_runtime.pyinstaller_hidden_imports(external_python_sandbox=False)
    assert build_win_runtime._windows_pyinstaller_collect_args(
        external_python_sandbox=False
    ) == build_runtime.pyinstaller_collect_args(external_python_sandbox=False)


def test_windows_pyinstaller_command_includes_web_extract_server(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: list[str] = []

    def fake_run(command, **kwargs):
        captured.extend(command)
        dist_path = Path(command[command.index("--distpath") + 1])
        output = dist_path / "box-agent-acp"
        output.mkdir(parents=True)
        (output / "box-agent-acp.exe").write_bytes(b"exe")
        return CompletedProcess(command, 0)

    monkeypatch.setattr(build_win_runtime.subprocess, "run", fake_run)
    bin_dir = tmp_path / "box-agent-runtime" / "bin"

    build_win_runtime._run_pyinstaller(bin_dir)

    hidden_pairs = list(zip(captured, captured[1:]))
    assert (
        "--hidden-import",
        "box_agent.mcp_servers.web_extract_server",
    ) in hidden_pairs
    assert (bin_dir / "box-agent-acp.exe").is_file()
    assert ("--exclude-module", "ipykernel") in hidden_pairs
    assert ("--exclude-module", "sklearn") in hidden_pairs
    assert ("--hidden-import", "PIL.Image") in hidden_pairs


def test_windows_manifest_advertises_bundled_web_extract_mcp(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "box-agent-runtime"
    runtime_dir.mkdir()

    build_win_runtime._write_manifest(runtime_dir, "0.9.7")

    manifest = json.loads(
        (runtime_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["platform"] == "win32"
    assert manifest["arch"] == "x64"
    assert manifest["entry"] == "bin/box-agent-acp.exe"
    assert manifest["managed_mcp_config_version"] == 1
    assert manifest["external_python_sandbox"] is True
    assert manifest["bundled_stable_runtimes"] == []
    assert manifest["mcp_servers"] == {
        "box-agent-web-extract": {
            "entry": "bin/box-agent-acp.exe",
            "args": ["--web-extract-mcp"],
            "transport": "stdio",
        }
    }
    assert (runtime_dir / "VERSION").read_text(encoding="utf-8") == "0.9.7\n"


def test_windows_legacy_manifest_lists_its_bundled_tools(tmp_path: Path) -> None:
    build_win_runtime._write_manifest(
        tmp_path, "0.9.7", external_python_sandbox=False
    )
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_python_sandbox"] is False
    assert manifest["bundled_stable_runtimes"] == ["portable_git", "python", "node"]


@pytest.mark.parametrize("bundled", [False, True])
@pytest.mark.parametrize("exe_only", [False, True])
def test_windows_build_entry_preserves_selected_profile_and_existing_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bundled: bool, exe_only: bool
) -> None:
    runtime_dir = tmp_path / "output" / "box-agent-runtime"
    python_exe = runtime_dir / "runtime" / "python" / "python.exe"
    old_node = runtime_dir / "runtimes" / "node" / "existing.txt"
    if exe_only:
        python_exe.parent.mkdir(parents=True)
        python_exe.write_bytes(b"existing python")
        old_node.parent.mkdir(parents=True)
        old_node.write_bytes(b"existing node")

    def install_python(_runtime_dir: Path) -> None:
        python_exe.parent.mkdir(parents=True)
        python_exe.write_bytes(b"bundled python")

    build = Mock()
    installers = {
        "_install_portable_git_win": Mock(),
        "_install_portable_python_win": Mock(side_effect=install_python),
        "_install_sandbox_packages_win": Mock(),
        "_install_node_win": Mock(),
    }
    monkeypatch.setattr(build_win_runtime, "_ensure_win", lambda: None)
    monkeypatch.setattr(build_win_runtime, "_install_runtime_extras", lambda: None)
    monkeypatch.setattr(build_win_runtime, "_load_build_dependencies", lambda: None)
    monkeypatch.setattr(build_win_runtime, "BUILD_TOOLS_CACHE", tmp_path / "cache", raising=False)
    monkeypatch.setattr(build_win_runtime, "_run_pyinstaller", build)
    for name, installer in installers.items():
        monkeypatch.setattr(build_win_runtime, name, installer, raising=False)
    args = [
        "build_win_runtime.py", "--version", "0.9.7",
        "--output", str(runtime_dir.parent), "--no-tar",
    ]
    if bundled:
        args.append("--bundled-python-sandbox")
    if exe_only:
        args.append("--exe-only")
    monkeypatch.setattr(build_win_runtime.sys, "argv", args)

    build_win_runtime.main()

    build.assert_called_once_with(runtime_dir / "bin", external_python_sandbox=not bundled)
    manifest = json.loads((runtime_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_python_sandbox"] is not bundled
    expected_components = ["portable_git", "python", "node"] if bundled else []
    assert manifest["bundled_stable_runtimes"] == expected_components
    for name, installer in installers.items():
        if bundled and not exe_only:
            target = python_exe if name == "_install_sandbox_packages_win" else runtime_dir
            installer.assert_called_once_with(target)
        else:
            installer.assert_not_called()
    if exe_only:
        assert python_exe.read_bytes() == b"existing python"
        assert old_node.read_bytes() == b"existing node"
    elif not bundled:
        assert not (runtime_dir / "runtime").exists()
        assert not (runtime_dir / "runtimes").exists()
