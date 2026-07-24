"""Shared deliverable-intent text helpers for completion routing."""

from __future__ import annotations

import re
from typing import Final


DELIVERABLE_INTENT_KEYWORDS: Final[tuple[str, ...]] = (
    "做一份",
    "做一个",
    "制作",
    "生成",
    "创建",
    "新建",
    "导出",
    "输出",
    "保存",
    "另出",
    "继续",
    "接着",
    "补完",
    "完成",
    "write",
    "create",
    "generate",
    "make",
    "build",
    "export",
    "save",
    "continue",
    "resume",
    "finish",
)

NEGATED_FORMAT_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:不要|不用|禁止|避免|无需|不能|不可|别|"
    r"\b(?:do\s+not|don't|without|avoid|never|no)\b)"
    r"(?:[^，。；;.!?\n]|\.(?=[A-Za-z0-9]))*",
    re.IGNORECASE,
)


def has_deliverable_intent(text: str) -> bool:
    normalized = text.strip().lower()
    return bool(normalized) and any(
        keyword in normalized for keyword in DELIVERABLE_INTENT_KEYWORDS
    )


def strip_negated_format_clauses(text: str) -> str:
    return NEGATED_FORMAT_CLAUSE_RE.sub(" ", text)
