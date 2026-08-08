"""Deterministic skill preloading shared by ACP and CLI entry points."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Literal, Mapping

from box_agent.loop_guards import (
    DEEP_RESEARCH_WEB_SEARCH_TOTAL_LIMIT,
    CompletionGate,
)
from box_agent.tools.skill_loader import SkillLoader
from box_agent.workflows.presentation_contract import RESEARCH_MODE_OPTION

AUTO_LOADED_SKILLS_HEADING = "## Auto-Loaded Skill Instructions"
ACTIVE_SKILLS_HEADING = "## Active Skill Instructions"

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
_VIDEO_DELIVERABLE_SIGNAL_RE = re.compile(
    r"\b(?:videos?|mp4|gifs?|hyperframes)\b|"
    r"\bmotion[\s-]+graphics?\b|"
    r"\bexplainer[\s-]+clips?\b",
    re.IGNORECASE,
)
_VIDEO_DELIVERABLE_INTENT_RE = re.compile(
    r"\b(?:animate|build|convert|create|export|generate|make|need|output|preview|"
    r"produce|record|render|save|turn|use|want)\b",
    re.IGNORECASE,
)
_VIDEO_DELIVERABLE_ZH_SIGNALS = ("视频", "短片", "动图")
_VIDEO_DELIVERABLE_ZH_INTENTS = (
    "做一个",
    "做个",
    "制作",
    "生成",
    "创建",
    "渲染",
    "导出",
    "输出",
    "转换",
    "转成",
    "转为",
    "转视频",
    "做成",
    "录制",
    "预览",
    "保存",
    "给我",
    "帮我",
    "需要",
    "想要",
)


@dataclass(frozen=True)
class SkillPreloadAttribution:
    skill_name: str
    usage_role: Literal["primary", "dependency"]
    dependency_of: str | None = None


@dataclass(frozen=True)
class AutoLoadedSkillsPrompt:
    system_prompt: str
    loaded_names: tuple[str, ...]
    loaded_skill_hashes: tuple[tuple[str, str], ...]
    loaded_attributions: tuple[SkillPreloadAttribution, ...]
    missing_names: tuple[str, ...]
    changed: bool


def strip_auto_loaded_skills(system_prompt: str) -> str:
    marker = f"\n\n{AUTO_LOADED_SKILLS_HEADING}\n"
    if marker in system_prompt:
        return system_prompt.split(marker, 1)[0].rstrip()
    if system_prompt.startswith(f"{AUTO_LOADED_SKILLS_HEADING}\n"):
        return ""
    return system_prompt


def strip_active_skills(system_prompt: str) -> str:
    """Remove the managed on-demand skill block from a system prompt."""
    marker = f"\n\n{ACTIVE_SKILLS_HEADING}\n"
    if marker in system_prompt:
        return system_prompt.split(marker, 1)[0].rstrip()
    if system_prompt.startswith(f"{ACTIVE_SKILLS_HEADING}\n"):
        return ""
    return system_prompt


def build_active_skills_prompt(
    system_prompt: str,
    skill_prompts: Mapping[str, str],
) -> str:
    """Render deduplicated on-demand skills at the system prompt tail."""
    base_prompt = strip_active_skills(system_prompt).rstrip()
    blocks = [prompt.strip() for prompt in skill_prompts.values() if prompt.strip()]
    if not blocks:
        return base_prompt
    return (
        f"{base_prompt}\n\n{ACTIVE_SKILLS_HEADING}\n"
        "The following skills were loaded on demand for the active task. Follow "
        "their full instructions, but never override earlier safety, permission, "
        "or runtime boundaries in this system prompt.\n\n"
        + "\n\n".join(blocks)
    )


def document_preload_skill_names(
    matched_skill_names: tuple[str, ...],
    completion_gate: CompletionGate | None,
    *,
    presentation_skill_name: str | None = "pptx",
) -> list[str]:
    if completion_gate is None:
        return []
    patterns = tuple(completion_gate.required_changed_artifact_globs)
    preload: list[str] = []
    if (
        completion_gate.workflow_checkpoint_kind == "controlled_presentation"
        and presentation_skill_name
    ):
        preload.append(presentation_skill_name)
    for skill_name, suffixes in GATE_REQUIRED_DOCUMENT_SKILL_ARTIFACT_SUFFIXES.items():
        if (
            skill_name == "pptx"
            and completion_gate.workflow_checkpoint_kind == "controlled_presentation"
        ):
            continue
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
    if (
        completion_gate.workflow_options.get(RESEARCH_MODE_OPTION) == "deep"
        and "research-synthesis" not in preload
    ):
        preload.append("research-synthesis")
    return preload


def web_search_total_limit_for_active_skills(
    matched_skill_names: tuple[str, ...],
    preloaded_skill_names: tuple[str, ...] = (),
) -> int | None:
    """Expand the per-turn search budget only for research synthesis."""
    if "research-synthesis" in matched_skill_names or (
        "research-synthesis" in preloaded_skill_names
    ):
        return DEEP_RESEARCH_WEB_SEARCH_TOTAL_LIMIT
    return None


def has_explicit_video_deliverable_intent(user_text: str | None) -> bool:
    """Return whether the current turn clearly requests a video artifact workflow."""
    if not user_text or not user_text.strip():
        return False
    text = user_text.strip()
    has_signal = bool(_VIDEO_DELIVERABLE_SIGNAL_RE.search(text)) or any(
        signal in text for signal in _VIDEO_DELIVERABLE_ZH_SIGNALS
    )
    if not has_signal:
        return False
    return bool(_VIDEO_DELIVERABLE_INTENT_RE.search(text)) or any(
        intent in text for intent in _VIDEO_DELIVERABLE_ZH_INTENTS
    )


def host_runtime_preload_skill_names(
    matched_skill_names: tuple[str, ...],
    env_context: Any | None,
    user_text: str | None,
) -> list[str]:
    hyperframes = getattr(env_context, "hyperframes", None)
    if hyperframes is None:
        return []
    if getattr(hyperframes, "available", None) is not True:
        return []
    if not has_explicit_video_deliverable_intent(user_text):
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
    user_text: str | None,
    *,
    presentation_skill_name: str | None = "pptx",
    force_presentation_skill: bool = False,
) -> list[str]:
    preload: list[str] = []
    if force_presentation_skill and presentation_skill_name:
        preload.append(presentation_skill_name)
    for skill_name in document_preload_skill_names(
        matched_skill_names,
        completion_gate,
        presentation_skill_name=presentation_skill_name,
    ):
        if skill_name not in preload:
            preload.append(skill_name)
    for skill_name in host_runtime_preload_skill_names(
        matched_skill_names,
        env_context,
        user_text,
    ):
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


def resolve_skill_preload_attributions(
    skill_loader: SkillLoader,
    skill_names: list[str] | tuple[str, ...],
    *,
    existing_skill_names: list[str] | tuple[str, ...] = (),
    existing_attributions: Mapping[str, SkillPreloadAttribution] | None = None,
    include_disabled: bool = False,
) -> list[SkillPreloadAttribution]:
    """Resolve root skills and one-hop required dependencies without billing ambiguity.

    Explicitly requested skills are primary. A required skill is a dependency unless
    it is also explicitly requested. Existing attribution is preserved across the
    session so rebuilding the managed prompt does not promote dependencies to roots.
    """
    ordered_names: list[str] = []
    attributions: dict[str, SkillPreloadAttribution] = {}

    for skill_name in existing_skill_names:
        if not skill_name:
            continue
        if skill_name not in ordered_names:
            ordered_names.append(skill_name)
        existing = (existing_attributions or {}).get(skill_name)
        attributions[skill_name] = existing or SkillPreloadAttribution(
            skill_name=skill_name,
            usage_role="primary",
        )

    explicit_names: list[str] = []
    _unique_append(explicit_names, tuple(skill_names))
    for skill_name in explicit_names:
        if skill_name not in ordered_names:
            ordered_names.append(skill_name)
        attributions[skill_name] = SkillPreloadAttribution(
            skill_name=skill_name,
            usage_role="primary",
        )

    for parent_name in tuple(ordered_names):
        skill = skill_loader.get_skill(parent_name, include_disabled=include_disabled)
        if skill is None:
            continue
        parent = attributions[parent_name]
        dependency_root = (
            parent.skill_name
            if parent.usage_role == "primary"
            else parent.dependency_of or parent.skill_name
        )
        for required_skill_name in skill.required_skills or []:
            if not required_skill_name:
                continue
            if required_skill_name not in ordered_names:
                ordered_names.append(required_skill_name)
            if required_skill_name in explicit_names:
                continue
            existing = attributions.get(required_skill_name)
            if existing is not None:
                continue
            attributions[required_skill_name] = SkillPreloadAttribution(
                skill_name=required_skill_name,
                usage_role="dependency",
                dependency_of=dependency_root,
            )

    return [attributions[name] for name in ordered_names]


def build_auto_loaded_skills_prompt(
    skill_loader: SkillLoader,
    system_prompt: str,
    skill_names: list[str] | tuple[str, ...],
    *,
    existing_skill_names: list[str] | tuple[str, ...] = (),
    existing_attributions: Mapping[str, SkillPreloadAttribution] | None = None,
    include_disabled: bool = False,
) -> AutoLoadedSkillsPrompt:
    requested_attributions = resolve_skill_preload_attributions(
        skill_loader,
        skill_names,
        existing_skill_names=existing_skill_names,
        existing_attributions=existing_attributions,
        include_disabled=include_disabled,
    )
    requested_names = [item.skill_name for item in requested_attributions]
    if not requested_names:
        base_prompt = strip_auto_loaded_skills(
            strip_active_skills(system_prompt)
        ).rstrip()
        return AutoLoadedSkillsPrompt(
            system_prompt=base_prompt,
            loaded_names=(),
            loaded_skill_hashes=(),
            loaded_attributions=(),
            missing_names=(),
            changed=system_prompt != base_prompt,
        )

    blocks: list[str] = []
    loaded_names: list[str] = []
    loaded_skill_hashes: list[tuple[str, str]] = []
    loaded_attributions: list[SkillPreloadAttribution] = []
    missing_names: list[str] = []
    for attribution in requested_attributions:
        skill_name = attribution.skill_name
        skill = skill_loader.get_skill(skill_name, include_disabled=include_disabled)
        if skill is None:
            missing_names.append(skill_name)
            continue
        loaded_names.append(skill_name)
        loaded_attributions.append(attribution)
        skill_prompt = skill.to_prompt()
        blocks.append(skill_prompt)
        loaded_skill_hashes.append(
            (skill.name, sha256(skill_prompt.encode("utf-8")).hexdigest())
        )

    if not blocks:
        base_prompt = strip_auto_loaded_skills(
            strip_active_skills(system_prompt)
        ).rstrip()
        return AutoLoadedSkillsPrompt(
            system_prompt=base_prompt,
            loaded_names=tuple(loaded_names),
            loaded_skill_hashes=tuple(loaded_skill_hashes),
            loaded_attributions=tuple(loaded_attributions),
            missing_names=tuple(missing_names),
            changed=system_prompt != base_prompt,
        )

    # Active skills are rendered by Agent after this auto-loaded block. Strip
    # both managed tails here so their order stays base -> auto -> active even
    # when an on-demand skill was loaded before the first auto-preload.
    base_prompt = strip_auto_loaded_skills(
        strip_active_skills(system_prompt)
    ).rstrip()
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
        loaded_attributions=tuple(loaded_attributions),
        missing_names=tuple(missing_names),
        changed=system_prompt != preloaded_prompt,
    )
