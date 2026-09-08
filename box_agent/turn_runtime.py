"""Pure turn-preparation helpers shared by host adapters.

The adapters retain SkillSelector lifecycle, rendering, warnings, and host
metadata.  This module only owns small state projections that must have the
same shape for cache fingerprinting in every host.
"""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from typing import Any


def sync_skill_cache_fingerprint_context(
    cache_context: MutableMapping[str, Any],
    *,
    matched_skill_names: Iterable[str] | None,
    preloaded_skill_names: Iterable[str],
) -> None:
    """Project current Skill names into an Agent cache context.

    Lists are copied so a later selector/preload mutation cannot silently
    change the fingerprint snapshot owned by the current Agent turn.
    """

    cache_context["filtered_skill_names"] = list(matched_skill_names or ())
    cache_context["preloaded_skill_names"] = list(preloaded_skill_names)


__all__ = ["sync_skill_cache_fingerprint_context"]
