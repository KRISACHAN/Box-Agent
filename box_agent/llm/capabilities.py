"""Capability queries for configured LLM adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def model_candidate_has_tag(candidate: Any, tag: str) -> bool:
    """Return whether a validated-looking model candidate declares one tag."""
    if not isinstance(candidate, Mapping):
        return False
    tags = candidate.get("tags")
    if not isinstance(tags, (list, tuple, set, frozenset)):
        return False
    return tag in tags


def image_input_support(llm: Any) -> bool | None:
    """Return declared image-input support, or ``None`` when it is unknown."""
    supports = getattr(type(llm), "supports", None)
    if supports is not None:
        supports = supports.__get__(llm, type(llm))
    elif hasattr(llm, "__dict__"):
        supports = vars(llm).get("supports")
    if callable(supports):
        try:
            declared = supports("image_input")
        except (TypeError, ValueError):
            declared = None
        if isinstance(declared, bool):
            return declared

    capabilities = getattr(llm, "capabilities", None)
    if isinstance(capabilities, Mapping):
        declared = capabilities.get("image_input")
        if isinstance(declared, bool):
            return declared

    model = str(getattr(llm, "model", "") or "").strip()
    candidates = tuple(getattr(llm, "auto_model_candidates", ()) or ())
    current = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, Mapping) and candidate.get("model") == model
        ),
        None,
    )
    if current is not None:
        return model_candidate_has_tag(current, "vision")

    normalized_model = model.lower()
    api_base = str(getattr(llm, "api_base", "") or "").lower()
    if "vision" in normalized_model or "deepseek-vl" in normalized_model:
        return True
    if "api.deepseek.com" in api_base or normalized_model.startswith("deepseek-"):
        return False
    return None


__all__ = ["image_input_support", "model_candidate_has_tag"]
