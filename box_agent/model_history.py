"""Shared markers for content omitted from model-facing history."""

from __future__ import annotations

from typing import Any


MODEL_HISTORY_PLACEHOLDER_PREFIXES = (
    "[Full tool-call argument omitted from model history]",
    "[Full file content omitted from model history]",
    "[Full tool output omitted from model history]",
)


def is_model_history_placeholder(value: Any) -> bool:
    """Return true when a value is an internal model-history placeholder."""
    return isinstance(value, str) and any(
        value.startswith(prefix) for prefix in MODEL_HISTORY_PLACEHOLDER_PREFIXES
    )
