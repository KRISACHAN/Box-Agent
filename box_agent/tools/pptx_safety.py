"""Safety guards for PPTX HTML-first export workflows."""

from __future__ import annotations

import re
from pathlib import Path


_BYPASS_ERROR = (
    "PPTX HTML self-check bypass blocked. Use scripts/html_to_editable_pptx.js, "
    "fix qa/html_self_check.json failures, or report "
    "Editable PPTX export: BLOCKED (HTML self-check failed)."
)

_NON_EXECUTABLE_STYLESHEET_SUFFIXES = {".css", ".less", ".sass", ".scss"}


def _has_skipcheck_name(text: str) -> bool:
    return bool(re.search(r"skip[-_ ]?check|skipcheck|bypass", text, re.IGNORECASE))


def _mentions_pptx_exporter(text: str) -> bool:
    lower = text.lower()
    return (
        "html_to_editable_pptx.js" in lower
        or "html-to-pptx.js" in lower
        or "dom-to-pptx.bundle.js" in lower
        or "domtopptx" in lower
        or "exporttopptx" in lower
    )


def _mentions_self_check(text: str) -> bool:
    lower = text.lower()
    return "html_self_check" in lower or "runselfcheck" in lower


def _looks_like_direct_dom_export(text: str) -> bool:
    lower = text.lower()
    return (
        ("dom-to-pptx.bundle.js" in lower or "domtopptx" in lower)
        and "exporttopptx" in lower
        and "html_self_check" not in lower
        and "runselfcheck" not in lower
    )


def _looks_like_self_check_removal(text: str) -> bool:
    lower = text.lower()
    return _mentions_self_check(text) and any(
        token in lower
        for token in (
            "replace",
            "writefilesync",
            "copyfile",
            "remove",
            "delete",
            "splice",
            "skip",
            "bypass",
            "comment out",
            "移除",
            "删除",
            "注释",
            "绕过",
        )
    )


def detect_pptx_self_check_bypass(path: str | None, text: str) -> str | None:
    """Detect attempts to create or execute a PPTX self-check bypass.

    This intentionally targets the bad failure mode observed in PPTX generation:
    creating a temporary exporter that removes ``runSelfCheck`` or calling the
    DOM-to-PPTX bundle directly after self-check fails. Normal inspection of the
    official exporter remains allowed.
    """
    file_path = Path(path) if path else None
    if file_path and file_path.suffix.lower() in _NON_EXECUTABLE_STYLESHEET_SUFFIXES:
        return None

    path_text = str(file_path.name if file_path else "")
    combined = f"{path_text}\n{text}"

    if _has_skipcheck_name(combined) and _mentions_pptx_exporter(combined):
        return _BYPASS_ERROR

    if _looks_like_direct_dom_export(combined):
        return _BYPASS_ERROR

    if _looks_like_self_check_removal(combined) and _mentions_pptx_exporter(combined):
        return _BYPASS_ERROR

    return None
