"""Protocol-independent Skill preload state transitions."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping, MutableSequence
from typing import Any

from box_agent.tools.skill_loader import SkillLoader
from box_agent.tools.skill_preload import (
    AutoLoadedSkillsPrompt,
    build_auto_loaded_skills_prompt,
)


def prepare_auto_loaded_skills(
    skill_loader: SkillLoader,
    system_prompt: str,
    skill_names: list[str] | tuple[str, ...],
    *,
    include_disabled: bool = False,
    preloaded_skill_names: MutableSequence[str],
    preloaded_skill_hashes: MutableMapping[str, str],
    preloaded_skill_attributions: MutableMapping[str, Any] | None = None,
    prompt_builder: Callable[..., AutoLoadedSkillsPrompt] = build_auto_loaded_skills_prompt,
) -> tuple[AutoLoadedSkillsPrompt, set[str]]:
    """Build and apply one auto-loaded Skill prompt transition.

    Prompt replacement, warnings, logging, and host-facing attribution remain
    adapter responsibilities.  This function only combines the shared
    builder with the collection transition so ACP and CLI cannot drift in
    which names/hashes they retain after a preload.
    """

    result = prompt_builder(
        skill_loader,
        system_prompt,
        skill_names,
        include_disabled=include_disabled,
    )
    unloaded_skill_names = apply_auto_loaded_skill_state(
        result,
        preloaded_skill_names=preloaded_skill_names,
        preloaded_skill_hashes=preloaded_skill_hashes,
        preloaded_skill_attributions=preloaded_skill_attributions,
    )
    return result, unloaded_skill_names


def apply_auto_loaded_skill_state(
    result: AutoLoadedSkillsPrompt,
    *,
    preloaded_skill_names: MutableSequence[str],
    preloaded_skill_hashes: MutableMapping[str, str],
    preloaded_skill_attributions: MutableMapping[str, Any] | None = None,
) -> set[str]:
    """Apply one preload result while preserving collection identities.

    Adapters retain warning, logging, prompt replacement, and host metadata
    decisions.  This helper only performs the shared state transition and
    returns names that were removed so each host can render them as before.
    """

    previous_skill_names = set(preloaded_skill_names)
    preloaded_skill_names[:] = result.loaded_names
    preloaded_skill_hashes.clear()
    preloaded_skill_hashes.update(result.loaded_skill_hashes)
    if preloaded_skill_attributions is not None:
        preloaded_skill_attributions.clear()
        preloaded_skill_attributions.update(
            {
                attribution.skill_name: attribution
                for attribution in result.loaded_attributions
            }
        )
    return previous_skill_names - set(result.loaded_names)


__all__ = ["apply_auto_loaded_skill_state", "prepare_auto_loaded_skills"]
