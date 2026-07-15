"""Deterministic skill preloading shared by ACP and CLI entry points."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from box_agent.loop_guards import CompletionGate
from box_agent.tools.skill_loader import SkillLoader

AUTO_LOADED_SKILLS_HEADING = "## Auto-Loaded Skill Instructions"

DOCUMENT_SKILL_ARTIFACT_SUFFIXES: dict[str, tuple[str, ...]] = {
    "pptx": (".pptx", ".ppt"),
    "docx": (".docx",),
    "xlsx": (".xlsx", ".xls"),
    "pdf": (".pdf",),
}
GATE_REQUIRED_DOCUMENT_SKILL_ARTIFACT_SUFFIXES: dict[str, tuple[str, ...]] = {
    "pptx": DOCUMENT_SKILL_ARTIFACT_SUFFIXES["pptx"],
    "docx": DOCUMENT_SKILL_ARTIFACT_SUFFIXES["docx"],
    "xlsx": DOCUMENT_SKILL_ARTIFACT_SUFFIXES["xlsx"],
}
HOST_RUNTIME_PRELOAD_SKILLS: frozenset[str] = frozenset({"hyperframes-video"})


@dataclass(frozen=True)
class AutoLoadedSkillsPrompt:
    system_prompt: str
    loaded_names: tuple[str, ...]
    loaded_skill_hashes: tuple[tuple[str, str], ...]
    missing_names: tuple[str, ...]
    changed: bool


def strip_auto_loaded_skills(system_prompt: str) -> str:
    marker = f"\n\n{AUTO_LOADED_SKILLS_HEADING}\n"
    if marker in system_prompt:
        return system_prompt.split(marker, 1)[0].rstrip()
    if system_prompt.startswith(f"{AUTO_LOADED_SKILLS_HEADING}\n"):
        return ""
    return system_prompt


def document_preload_skill_names(
    matched_skill_names: tuple[str, ...],
    completion_gate: CompletionGate | None,
) -> list[str]:
    if completion_gate is None:
        return []
    patterns = tuple(completion_gate.required_changed_artifact_globs)
    preload: list[str] = []
    for skill_name, suffixes in GATE_REQUIRED_DOCUMENT_SKILL_ARTIFACT_SUFFIXES.items():
        if any(suffix in pattern for pattern in patterns for suffix in suffixes):
            preload.append(skill_name)
    for skill_name in matched_skill_names:
        suffixes = DOCUMENT_SKILL_ARTIFACT_SUFFIXES.get(skill_name)
        if (
            skill_name not in preload
            and suffixes
            and any(suffix in pattern for pattern in patterns for suffix in suffixes)
        ):
            preload.append(skill_name)
    return preload


def host_runtime_preload_skill_names(
    matched_skill_names: tuple[str, ...],
    env_context: Any | None,
) -> list[str]:
    hyperframes = getattr(env_context, "hyperframes", None)
    if hyperframes is None:
        return []
    if getattr(hyperframes, "available", None) is not True:
        return []
    return [
        skill_name
        for skill_name in matched_skill_names
        if skill_name in HOST_RUNTIME_PRELOAD_SKILLS
    ]


def turn_preload_skill_names(
    matched_skill_names: tuple[str, ...],
    completion_gate: CompletionGate | None,
    env_context: Any | None,
) -> list[str]:
    preload: list[str] = []
    for skill_name in document_preload_skill_names(matched_skill_names, completion_gate):
        if skill_name not in preload:
            preload.append(skill_name)
    for skill_name in host_runtime_preload_skill_names(matched_skill_names, env_context):
        if skill_name not in preload:
            preload.append(skill_name)
    return preload


def _unique_append(target: list[str], values: list[str] | tuple[str, ...]) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def expand_required_skill_names(
    skill_loader: SkillLoader,
    skill_names: list[str] | tuple[str, ...],
    *,
    existing_skill_names: list[str] | tuple[str, ...] = (),
    include_disabled: bool = False,
) -> list[str]:
    requested_names: list[str] = []
    _unique_append(requested_names, tuple(existing_skill_names))
    _unique_append(requested_names, tuple(skill_names))

    expanded_names: list[str] = []
    for skill_name in requested_names:
        if skill_name not in expanded_names:
            expanded_names.append(skill_name)
        skill = skill_loader.get_skill(skill_name, include_disabled=include_disabled)
        if skill is None:
            continue
        for required_skill_name in skill.required_skills or []:
            if required_skill_name not in expanded_names:
                expanded_names.append(required_skill_name)
    return expanded_names


def build_auto_loaded_skills_prompt(
    skill_loader: SkillLoader,
    system_prompt: str,
    skill_names: list[str] | tuple[str, ...],
    *,
    existing_skill_names: list[str] | tuple[str, ...] = (),
    include_disabled: bool = False,
) -> AutoLoadedSkillsPrompt:
    requested_names = expand_required_skill_names(
        skill_loader,
        skill_names,
        existing_skill_names=existing_skill_names,
        include_disabled=include_disabled,
    )
    if not requested_names:
        return AutoLoadedSkillsPrompt(
            system_prompt=system_prompt,
            loaded_names=(),
            loaded_skill_hashes=(),
            missing_names=(),
            changed=False,
        )

    blocks: list[str] = []
    loaded_names: list[str] = []
    loaded_skill_hashes: list[tuple[str, str]] = []
    missing_names: list[str] = []
    for skill_name in requested_names:
        skill = skill_loader.get_skill(skill_name, include_disabled=include_disabled)
        if skill is None:
            missing_names.append(skill_name)
            continue
        loaded_names.append(skill_name)
        skill_prompt = skill.to_prompt()
        blocks.append(skill_prompt)
        loaded_skill_hashes.append(
            (skill.name, sha256(skill_prompt.encode("utf-8")).hexdigest())
        )

    if not blocks:
        return AutoLoadedSkillsPrompt(
            system_prompt=system_prompt,
            loaded_names=tuple(loaded_names),
            loaded_skill_hashes=tuple(loaded_skill_hashes),
            missing_names=tuple(missing_names),
            changed=False,
        )

    base_prompt = strip_auto_loaded_skills(system_prompt).rstrip()
    preloaded_prompt = (
        f"{base_prompt}\n\n{AUTO_LOADED_SKILLS_HEADING}\n"
        "The following matched or required skills are preloaded because this turn "
        "requires a concrete deliverable or host-provided runtime workflow. Follow "
        "their full instructions before planning, delegating, or authoring the "
        "artifact.\n\n"
        + "\n\n".join(blocks)
    )
    return AutoLoadedSkillsPrompt(
        system_prompt=preloaded_prompt,
        loaded_names=tuple(loaded_names),
        loaded_skill_hashes=tuple(loaded_skill_hashes),
        missing_names=tuple(missing_names),
        changed=system_prompt != preloaded_prompt,
    )
