"""Composition entry point for automatic deliverable completion gates."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from .artifacts import OUTPUT_SUBDIR
from .delivery import has_deliverable_intent, strip_negated_format_clauses
from .loop_guards import CompletionGate, artifact_signatures_for_globs
from .turn_policy import text_is_short_acknowledgement
from .workflows.presentation_routing import build_presentation_completion_gate


_PENDING_GATE_CANCEL_PHRASES: Final[tuple[str, ...]] = (
    "取消",
    "不用继续",
    "不要继续",
    "不做这个",
    "先不做",
    "换个任务",
    "新任务",
    "stop",
    "cancel",
    "never mind",
)

_PENDING_GATE_CONTINUE_PHRASES: Final[tuple[str, ...]] = (
    "继续",
    "接着",
    "补完",
    "完成",
    "输出html",
    "生成html",
    "渲染html",
    "continue",
    "resume",
    "finish",
    "go on",
    "output html",
    "render html",
)

_GENERIC_COMPLETION_GATE_PATTERNS: Final[
    tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
] = (
    (
        ("docx", "word", "简历", "文档"),
        (f"{OUTPUT_SUBDIR}/**/*.docx",),
    ),
    (
        ("xlsx", "excel", "spreadsheet", "表格"),
        (f"{OUTPUT_SUBDIR}/**/*.xlsx", f"{OUTPUT_SUBDIR}/**/*.xls"),
    ),
    (
        ("html", "网页", "报告", "md格式", "markdown"),
        (
            f"{OUTPUT_SUBDIR}/**/*.html",
            f"{OUTPUT_SUBDIR}/**/*.htm",
            f"{OUTPUT_SUBDIR}/**/*.md",
            f"{OUTPUT_SUBDIR}/**/*.pdf",
        ),
    ),
)

_IMAGE_ARTIFACT_GLOBS: Final[tuple[str, ...]] = (
    f"{OUTPUT_SUBDIR}/**/*.png",
    f"{OUTPUT_SUBDIR}/**/*.jpg",
    f"{OUTPUT_SUBDIR}/**/*.jpeg",
    f"{OUTPUT_SUBDIR}/**/*.webp",
)

_NATIVE_IMAGE_ACTION_KEYWORDS: Final[tuple[str, ...]] = (
    "生图",
    "生成一张",
    "画一张",
    "绘制一张",
    "生成图片",
    "生成图像",
    "generate an image",
    "create an image",
    "draw an image",
    "image generation",
    "text-to-image",
)

_NATIVE_IMAGE_OUTPUT_KEYWORDS: Final[tuple[str, ...]] = (
    "图片",
    "图像",
    "插画",
    "海报",
    "封面",
    "信息图",
    "全景图",
    "png",
    "jpg",
    "jpeg",
    "webp",
    "image",
    "illustration",
    "poster",
    "infographic",
)

_NON_NATIVE_IMAGE_DELIVERY_KEYWORDS: Final[tuple[str, ...]] = (
    "html",
    "svg",
    "网页",
    "web page",
    "截图",
    "screenshot",
    "ppt",
    "pptx",
    "powerpoint",
    "幻灯片",
    "演示文稿",
    "报告",
)


def _is_native_image_generation_request(
    text: str,
    positive_format_text: str,
) -> bool:
    has_action = any(keyword in text for keyword in _NATIVE_IMAGE_ACTION_KEYWORDS)
    has_image_output = any(
        keyword in text for keyword in _NATIVE_IMAGE_OUTPUT_KEYWORDS
    )
    has_non_native_delivery = any(
        keyword in positive_format_text
        for keyword in _NON_NATIVE_IMAGE_DELIVERY_KEYWORDS
    )
    return has_action and has_image_output and not has_non_native_delivery


def cancels_pending_completion_gate(user_text: str) -> bool:
    """Return whether the user explicitly abandons a retained deliverable."""
    normalized = " ".join(user_text.casefold().split())
    return bool(normalized) and any(
        phrase in normalized for phrase in _PENDING_GATE_CANCEL_PHRASES
    )


def should_resume_pending_completion_gate(
    user_text: str,
    *,
    waiting_for_user_input: bool,
) -> bool:
    """Recognize an answer or terse continuation of a retained deliverable."""
    normalized = " ".join(user_text.casefold().split()).strip()
    if not normalized or cancels_pending_completion_gate(normalized):
        return False
    if waiting_for_user_input:
        return True
    compact = normalized.replace(" ", "")
    if len(normalized) <= 80 and any(
        phrase in normalized or phrase.replace(" ", "") in compact
        for phrase in _PENDING_GATE_CONTINUE_PHRASES
    ):
        return True
    return text_is_short_acknowledgement(normalized)


def completion_gate_has_workflow_lifecycle(gate: CompletionGate) -> bool:
    """Return whether a workflow owns cross-turn state for this gate."""
    return gate.workflow_checkpoint_kind is not None


def build_auto_completion_gate(
    user_text: str,
    workspace_dir: str | Path,
) -> CompletionGate | None:
    """Create an evidence-backed gate for a recognized deliverable request."""
    if not has_deliverable_intent(user_text):
        return None

    presentation_gate = build_presentation_completion_gate(
        user_text,
        workspace_dir,
    )
    if presentation_gate is not None:
        return presentation_gate

    text = user_text.strip().lower()
    positive_format_text = strip_negated_format_clauses(text)
    native_image_generation = _is_native_image_generation_request(
        text,
        positive_format_text,
    )
    patterns: list[str] = (
        list(_IMAGE_ARTIFACT_GLOBS) if native_image_generation else []
    )
    if not native_image_generation:
        for keywords, artifact_patterns in _GENERIC_COMPLETION_GATE_PATTERNS:
            if any(keyword in positive_format_text for keyword in keywords):
                patterns.extend(artifact_patterns)
    if not patterns:
        return None

    deduped_patterns = tuple(dict.fromkeys(patterns))
    workspace = str(workspace_dir)
    return CompletionGate(
        required_tools=(
            frozenset({"generate_image"})
            if native_image_generation
            else frozenset()
        ),
        restrict_tools_until_required_succeed=native_image_generation,
        required_changed_artifact_globs=deduped_patterns,
        baseline_artifact_signatures=artifact_signatures_for_globs(
            deduped_patterns,
            workspace,
        ),
        max_continuations=3,
        deadline_seconds=900.0,
    )
