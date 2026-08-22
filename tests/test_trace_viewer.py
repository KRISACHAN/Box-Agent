from __future__ import annotations

import os
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NODE_TEST = PROJECT_ROOT / "tests" / "js" / "trace_model.test.js"
VIEWER_ROOT = PROJECT_ROOT / "box_agent" / "trace_viewer"
VIEWER_INDEX = VIEWER_ROOT / "index.html"


class _ViewerDocument(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.csp = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(str(attributes["id"]))
        if tag == "script" and attributes.get("src"):
            self.scripts.append(str(attributes["src"]))
        if tag == "link" and attributes.get("rel") == "stylesheet" and attributes.get("href"):
            self.stylesheets.append(str(attributes["href"]))
        if tag == "meta" and attributes.get("http-equiv", "").lower() == "content-security-policy":
            self.csp = str(attributes.get("content") or "")


def test_trace_model_node_suite() -> None:
    """A parser/correlation regression must fail in the real JS runtime."""

    node = os.environ.get("BOX_AGENT_NODE") or shutil.which("node")
    if node is None:
        pytest.skip("node is required for trace viewer model tests")

    result = subprocess.run(
        [node, "--test", str(NODE_TEST)],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def _viewer_document() -> _ViewerDocument:
    document = _ViewerDocument()
    document.feed(VIEWER_INDEX.read_text(encoding="utf-8"))
    return document


def test_viewer_document_exposes_each_diagnostic_region() -> None:
    """Removing a primary diagnostic pane must break the packaged page contract."""

    document = _viewer_document()

    assert {
        "summary-strip",
        "turn-list",
        "waterfall-view",
        "conversation-view",
        "events-view",
        "inspector",
    } <= document.ids


def test_viewer_document_exposes_directory_overview_and_dismissible_inspector() -> None:
    """The catalog and mobile inspector must have explicit navigation controls."""

    document = _viewer_document()

    assert {
        "overview-view",
        "open-directory",
        "directory-input",
        "directory-dialog",
        "directory-path",
        "load-directory-path",
        "trace-catalog",
        "detail-view",
        "all-traces",
        "close-inspector",
        "inspector-backdrop",
    } <= document.ids


def test_viewer_document_loads_only_local_assets_and_connects_only_to_its_service() -> None:
    """Adding a remote asset or connection target must fail the local-only boundary."""

    document = _viewer_document()

    assert document.scripts == ["trace_model.js", "app.js"]
    assert document.stylesheets == ["styles.css"]
    assert "connect-src 'self'" in document.csp
    assert all("://" not in asset for asset in document.scripts + document.stylesheets)


def test_trace_viewer_launcher_opens_the_packaged_index(monkeypatch) -> None:
    """Pointing the launcher at any file except the shipped index is a bug."""

    from box_agent.trace_viewer import launcher

    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda uri: opened.append(uri) or True)

    path = launcher.launch_trace_viewer()

    assert path == VIEWER_INDEX.resolve()
    assert opened == [VIEWER_INDEX.resolve().as_uri()]


def test_trace_viewer_launcher_reports_the_manual_path_when_browser_open_fails(
    monkeypatch,
) -> None:
    """A browser integration failure must leave developers a usable path."""

    from box_agent.trace_viewer import launcher

    monkeypatch.setattr(launcher.webbrowser, "open", lambda _uri: False)

    with pytest.raises(RuntimeError, match=r"open this file manually.*index\.html"):
        launcher.launch_trace_viewer()


def test_trace_viewer_cli_dispatches_before_configuration(monkeypatch) -> None:
    """Broken or absent LLM config must not block local trace diagnostics."""

    import box_agent.cli as cli

    launched: list[bool] = []
    monkeypatch.setattr(sys, "argv", ["box-agent", "trace-viewer"])
    monkeypatch.setattr(cli, "launch_trace_viewer", lambda: launched.append(True) or VIEWER_INDEX)
    monkeypatch.setattr(
        cli.Config,
        "_ensure_user_config",
        lambda: (_ for _ in ()).throw(AssertionError("configuration was touched")),
    )

    assert cli.main() == 0
    assert launched == [True]


def test_built_wheel_contains_viewer_assets_without_bytecode_cache() -> None:
    """Publishing the viewer must include assets but exclude local import caches."""

    wheels = sorted((PROJECT_ROOT / "dist").glob("box_agent-*.whl"))
    if not wheels:
        pytest.skip("build the wheel before running package-content verification")
    with zipfile.ZipFile(wheels[-1]) as archive:
        names = set(archive.namelist())

    assert {
        "box_agent/trace_viewer/index.html",
        "box_agent/trace_viewer/styles.css",
        "box_agent/trace_viewer/trace_model.js",
        "box_agent/trace_viewer/app.js",
    } <= names
    assert not any(
        name.startswith("box_agent/trace_viewer/__pycache__/") or name.endswith(".pyc")
        for name in names
    )


def test_built_sdist_contains_viewer_assets_without_bytecode_cache() -> None:
    """The source archive must apply the same viewer packaging boundary as wheels."""

    archives = sorted((PROJECT_ROOT / "dist").glob("box_agent-*.tar.gz"))
    if not archives:
        pytest.skip("build the sdist before running package-content verification")
    with tarfile.open(archives[-1], "r:gz") as archive:
        names = {member.name for member in archive.getmembers()}

    expected_suffixes = {
        "box_agent/trace_viewer/index.html",
        "box_agent/trace_viewer/styles.css",
        "box_agent/trace_viewer/trace_model.js",
        "box_agent/trace_viewer/app.js",
    }
    assert all(any(name.endswith(suffix) for name in names) for suffix in expected_suffixes)
    assert not any("/trace_viewer/__pycache__/" in name or name.endswith(".pyc") for name in names)
