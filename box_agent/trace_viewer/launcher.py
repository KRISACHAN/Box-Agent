"""Open the packaged static trace viewer without starting a local service."""

from __future__ import annotations

from pathlib import Path
import webbrowser


def viewer_path() -> Path:
    """Return the installed viewer document, failing clearly if packaging omitted it."""

    path = Path(__file__).with_name("index.html").resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Trace viewer asset not found: {path}")
    return path


def launch_trace_viewer(*, open_browser: bool = True) -> Path:
    """Open the static viewer and return its absolute path."""

    path = viewer_path()
    if open_browser and not webbrowser.open(path.as_uri()):
        raise RuntimeError(f"Could not open browser; open this file manually: {path}")
    return path
