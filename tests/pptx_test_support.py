"""Optional host-runtime checks shared by PPTX integration test runners."""

from __future__ import annotations

import subprocess

import pytest


def skip_unavailable_pptx_runtime(result: subprocess.CompletedProcess[str]) -> None:
    """Skip missing host dependencies, not script, rendering, or QA failures."""
    if result.returncode == 0:
        return
    output = result.stdout + result.stderr
    unavailable = (
        "Cannot find module 'playwright'",
        "Missing dependency: playwright",
        "Executable doesn't exist",
        "Playwright Chromium is not available",
    )
    if any(marker in output for marker in unavailable):
        pytest.skip("Managed Playwright browser is unavailable")
    if any(marker in output for marker in (
        "Cannot find module '@napi-rs/canvas'",
        "Missing dependency: @napi-rs/canvas",
    )):
        pytest.skip("Managed Canvas dependency is unavailable")
