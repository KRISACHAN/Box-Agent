"""Loop guards & continuation nudges for the agent execution loop.

These are the *pure, stateless* building blocks behind the family of
opt-in circuit breakers that keep :func:`box_agent.core.run_agent_loop`
from flailing or stopping prematurely:

- tool-call budget messages (cap repeated web_search etc.),
- the completion gate (force continuation until verifiable evidence
  exists — borrowed in spirit from oh-my-codex's Stop gate, but
  evidence-based rather than prose-pattern-based),
- the near-limit and no-progress wrap-up nudges.

Everything here is side-effect-free (apart from read-only filesystem
stats for artifact checks) so it can be unit-tested in isolation. The
actual loop wiring — counters, one-shot flags, message injection — stays
in ``core`` where the loop state lives.

Where to put things when adding a new circuit breaker:

- Pure logic (decide *whether* to fire, build *what text* to inject,
  constants/thresholds) → here, as a function or dataclass that takes
  loop facts as plain arguments and returns a value. No ``yield``, no
  ``messages`` mutation, no reference to loop-local variables.
- Wiring (the counters/flags it reads, the ``messages.append`` +
  ``yield InjectedMessageEvent``, the ``continue``/``return``) → in
  ``core.run_agent_loop``, calling into the pure helper here.

This split keeps ``core`` focused on control flow and keeps every
breaker's decision logic independently testable.
"""

from __future__ import annotations

import glob
import json
import re
import shlex
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# ── Constants ────────────────────────────────────────────────────

WEB_SEARCH_TOOL_NAME: Final = "web_search"
WEB_SEARCH_BATCH_SIZE: Final = 6
WEB_SEARCH_TOTAL_LIMIT: Final = 24
OUTPUT_SUBDIR: Final = "output"
_CONTROLLED_PPTX_SCRIPTS_DIR: Final = (
    Path(__file__).resolve().parent
    / "skills"
    / "document-skills"
    / "pptx"
    / "scripts"
)


def _controlled_pptx_command(script_name: str, arguments: str) -> str:
    script_path = shlex.quote(str(_CONTROLLED_PPTX_SCRIPTS_DIR / script_name))
    return f"${{BOX_AGENT_NODE:-node}} {script_path} {arguments}"

# Per-turn call caps for tools the model tends to over-request.
TOOL_CALL_LIMITS: Final[dict[str, int]] = {
    WEB_SEARCH_TOOL_NAME: WEB_SEARCH_TOTAL_LIMIT,
}

# Setup/bookkeeping tools that must NOT count toward the final-summary
# wrap-up threshold. That threshold targets process-log answers after many
# *substantive* tool calls; loading skills, publishing the plan/todos, or
# touching memory are workflow scaffolding, not the activity it targets.
# Counting them tripped the wrap-up nudge before real work began (notably in
# multi-stage PPT / expert-team flows).
FINAL_SUMMARY_EXCLUDED_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "get_skill",
        "plan_write",
        "todo_write",
        "todo_read",
        "memory_read",
        "memory_write",
        "memory_search",
    }
)

# Workflow scaffolding must not consume the hard delivery budget. These calls
# keep the UI and session state coherent, but do not advance or regress the
# actual presentation artifact. ``request_user_input`` is also exempt because
# a faithful pause should never be rejected merely because discovery used the
# remaining artifact-work budget.
PRESENTATION_BUDGET_EXEMPT_TOOLS: Final[frozenset[str]] = (
    FINAL_SUMMARY_EXCLUDED_TOOLS | frozenset({"request_user_input"})
)

# Reserve this many trailing steps for synthesis (near-limit wrap-up).
WRAPUP_REMAINING: Final[int] = 3

# Abort after this many consecutive all-empty-args tool_call turns.
EMPTY_ARGS_LIMIT: Final[int] = 2

# Stop a provider stream before a short exact pattern can flood the UI and
# conversation history. Whitespace is ignored so relays that alternate a tag
# with blank lines are still caught, while the minimum pattern length and
# repeat count keep ordinary prose out of the guard.
STREAM_REPEAT_MIN_PATTERN_CHARS: Final[int] = 4
STREAM_REPEAT_MAX_PATTERN_CHARS: Final[int] = 80
STREAM_REPEAT_LIMIT: Final[int] = 8
STREAM_REPEAT_WINDOW_CHARS: Final[int] = 4096
STREAM_REPEAT_MIN_CHUNKS: Final[int] = 4


def repeated_stream_pattern(text: str) -> str | None:
    """Return a short suffix pattern repeated pathologically in ``text``.

    Detection is deliberately limited to eight exact repeats of a 4-80
    character whitespace-insensitive pattern. The pattern must contain a
    letter or number and at least two distinct characters, which avoids
    tripping on normal markdown separators or a long punctuation run.
    """
    if not isinstance(text, str) or not text:
        return None
    compact = re.sub(r"\s+", "", text[-STREAM_REPEAT_WINDOW_CHARS:])
    max_pattern_length = min(
        STREAM_REPEAT_MAX_PATTERN_CHARS,
        len(compact) // STREAM_REPEAT_LIMIT,
    )
    for pattern_length in range(
        STREAM_REPEAT_MIN_PATTERN_CHARS,
        max_pattern_length + 1,
    ):
        repeated_length = pattern_length * STREAM_REPEAT_LIMIT
        suffix = compact[-repeated_length:]
        pattern = suffix[-pattern_length:]
        if (
            pattern * STREAM_REPEAT_LIMIT == suffix
            and any(char.isalnum() for char in pattern)
            and len(set(pattern)) >= 2
        ):
            return pattern
    return None


# ── Tool-call budget messages ────────────────────────────────────


def tool_call_budget_message(tool_name: str, limit: int) -> str:
    """Synthetic tool-error text returned once a tool's per-turn budget is hit."""
    return (
        f"Tool call budget reached for {tool_name} ({limit} calls this turn). "
        f"Do not call {tool_name} again; continue the current deliverable and "
        "final response from the evidence and tool results already collected. "
        "If anything is missing, briefly mark it as a gap instead of searching "
        "again."
    )


def tool_call_budget_wrapup_text(tool_name: str, limit: int) -> str:
    """One-shot wrap-up nudge injected when a tool's per-turn budget is hit."""
    return (
        f"⚠️ 本轮 {tool_name} 调用已达到预算上限（{limit} 次）。"
        f"现在请停止继续调用 {tool_name} 或继续联网搜索，"
        "仅基于已经获得的资料继续完成当前交付物和最终回复；缺口简要标注即可。"
    )


def total_tool_call_budget_message(limit: int) -> str:
    """Synthetic error once the per-loop total tool budget is exhausted."""
    return (
        f"Total tool call budget reached ({limit} calls this task). "
        "Do not call any more tools; synthesize the final answer from the "
        "evidence and tool results already collected."
    )


def total_tool_call_budget_wrapup_text(limit: int) -> str:
    """One-shot synthesis nudge for the total tool-call hard limit."""
    return (
        f"⚠️ 本任务工具调用总预算已达到上限（{limit} 次）。"
        "现在请停止调用任何工具，仅基于已有结果直接给出完整最终答案；"
        "缺口简要标注即可。"
    )


# ── Near-limit / no-progress wrap-up nudges ──────────────────────


def near_limit_wrapup_text(step: int, max_steps: int) -> str:
    """Reserve the final steps for synthesis: stop gathering, answer now.

    ``step`` is the 0-based loop index (as in ``run_agent_loop``).
    """
    remaining = max_steps - step
    return (
        f"⚠️ 步数预算即将用尽（已到第 {step + 1}/{max_steps} 步，约剩 {remaining} 步）。"
        "现在请停止调用任何工具、停止继续搜索或探索。"
        "仅基于你已经收集到的信息，在本轮直接给出完整、可独立阅读的最终答案/总结："
        "包含关键结论、数据、以及已产出的文件路径；若有未覆盖的缺口，简要标注即可，"
        "不要再去调查。"
    )


def no_progress_wrapup_text(no_progress_steps: int) -> str:
    """Force a synthesis after N consecutive steps with no useful tool result."""
    return (
        f"⚠️ 已连续 {no_progress_steps} 步没有取得有效进展"
        "（工具调用持续失败或无有用输出）。"
        "现在请立即停止调用任何工具、停止重试当前路径。"
        "仅基于你已经收集到的信息，在本轮直接给出完整、可独立阅读的"
        "最终答案/总结：包含关键结论、已知数据与已产出的文件路径；"
        "对未能获取的信息，简要标注为缺口即可，不要再继续调查。"
    )


# ── Mid-turn injection wrapper ───────────────────────────────────


def format_injected_message(text: str) -> str:
    """Wrap mid-stream user input so it steers the active task."""
    return (
        "The user sent the following message while the current task was already running.\n"
        "Treat it as mid-turn guidance, a constraint, or a clarification for the current task, "
        "not as a new standalone task.\n"
        "If it asks a question, answer it briefly if useful, then continue the original task. "
        "Do not stop or switch tasks unless the user explicitly asks you to stop, cancel, or change the task.\n\n"
        f"Mid-turn user message:\n{text}"
    )


# ── Suspected-truncation continuation ────────────────────────────
#
# Some upstream models / relay gateways stop a streamed text turn
# mid-sentence yet report a *normal* finish_reason ("stop"/"end_turn")
# or omit it entirely. The existing ``finish_reason in ("length",
# "max_tokens")`` guard in ``core`` never fires for these, so the half
# sentence is presented as a finished answer. The helpers below let the
# loop detect that case (conservatively) and inject a one-shot
# continuation so the model finishes the thought in the same message.

# Only consider a turn truncated when the model actually produced a
# non-trivial amount of text. Short replies legitimately end without
# terminal punctuation (e.g. a bare "好的" / a single path), and we do
# not want to chase those.
MIN_TOKENS_FOR_TRUNCATION_CHECK: Final[int] = 50

# Character-count fallback for the same "non-trivial reply" gate when the
# provider omits usage (or reports completion_tokens=0). Production
# gateways send usage, so this only guards degenerate/no-usage paths.
MIN_CHARS_FOR_TRUNCATION_CHECK: Final[int] = 40

# Trailing characters that count as a *clean* ending — if the text ends
# with any of these we never treat it as truncated. Covers CJK + ASCII
# sentence punctuation, closing quotes/brackets, colons/semicolons
# (section leads), markdown emphasis/inline-code closers, table pipes,
# and dashes.
_CLEAN_ENDING_CHARS: Final[frozenset[str]] = frozenset(
    "。．.！!？?…⋯"  # sentence terminators
    "」』）)】］]｝}＞>"  # closing brackets
    "\"'”’《》"  # quotes
    "：:；;"  # colon / semicolon (list or section lead-ins)
    "*`"  # markdown emphasis / inline code closers
    "|"  # table row
    "—～~"  # dashes / tilde
)

# Markdown structural last-lines that are complete as-is.
_TABLE_ROW_RE: Final = re.compile(r"^\s*\|.*\|\s*$")
_LIST_ITEM_RE: Final = re.compile(r"^\s*([-*+]|\d+[.)])\s+\S")
_ATOMIC_ASCII_REPLY_RE: Final = re.compile(
    r"^[A-Za-z0-9./\\:@+#%?&=~_-]{1,256}$"
)
_ATOMIC_REPLY_WORDS: Final[frozenset[str]] = frozenset(
    {"ok", "done", "success", "failed", "true", "false", "none", "null"}
)


def _looks_like_atomic_ascii_reply(text: str) -> bool:
    """Return true for complete machine-like status, ID, URL, or path replies."""
    if not _ATOMIC_ASCII_REPLY_RE.fullmatch(text):
        return False
    return (
        text.casefold() in _ATOMIC_REPLY_WORDS
        or (text.upper() == text and any(char.isalpha() for char in text))
        or any(char.isdigit() for char in text)
        or any(char in "._/\\:@+#%?&=~-" for char in text)
    )


def looks_like_truncated_output(text: str) -> bool:
    """Conservatively decide whether assistant text was cut mid-thought.

    Bias: prefer a false negative (miss a genuinely truncated reply that
    happens to end without punctuation) over a false positive (re-prompt
    a perfectly complete answer). Any "clean ending" signal — terminal
    punctuation, a closed bracket/quote/emphasis, or a complete markdown
    structural line (code fence, table row, list item) — returns False.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    if _looks_like_atomic_ascii_reply(stripped):
        return False
    if stripped[-1] in _CLEAN_ENDING_CHARS:
        return False
    last_line = stripped.rsplit("\n", 1)[-1].strip()
    if last_line.startswith("```"):
        return False
    if _TABLE_ROW_RE.match(last_line):
        return False
    if _LIST_ITEM_RE.match(last_line):
        return False
    return True


def reply_is_substantial(content_len: int, completion_tokens: int | None) -> bool:
    """Gate truncation handling to non-trivial replies only.

    Prefer the provider's completion-token count; fall back to character
    length when usage is absent or zero (degenerate / no-usage gateways),
    so a short reply without usage is not chased as a truncation.
    """
    if completion_tokens:
        return completion_tokens >= MIN_TOKENS_FOR_TRUNCATION_CHECK
    return content_len >= MIN_CHARS_FOR_TRUNCATION_CHECK


def truncation_continuation_text(tail: str) -> str:
    """One-shot continuation prompt for a suspected mid-sentence cutoff.

    Deliberately NOT wrapped by ``format_injected_message``: this is not
    a user interjection but a system-detected continuation instruction,
    so it must carry its own framing. ``tail`` is a short slice of where
    the previous reply stopped, to anchor the model.
    """
    return (
        "（系统提示）你上一条回复似乎在生成过程中被意外中断了，"
        f"结尾停在：“…{tail}”。\n"
        "请直接接着上面的结尾继续写完剩余内容，保持原有的格式、结构与语气；"
        "不要重复任何已经输出过的内容，也不要重新开头或重述前面已说过的部分，"
        "从断点处自然衔接即可。如果上一条其实已经表达完整，只需补一句简短收尾。"
    )


# ── Completion gate ──────────────────────────────────────────────


@dataclass(frozen=True)
class CompletionGate:
    """Opt-in completion gate for the agent loop.

    Borrowed in spirit from oh-my-codex's Stop gate, but deliberately
    evidence-based rather than prose-pattern-based: the gate only ever
    inspects *verifiable facts* (which tools produced a usable result,
    which artifact files exist) — never the assistant's wording.

    When supplied to :func:`box_agent.core.run_agent_loop`, a natural
    END_TURN (the model emits no tool calls) is intercepted: if any
    requirement is unmet, a continuation nudge naming the gaps is injected
    and the loop keeps going. A bounded ``max_continuations`` count plus an
    optional ``deadline_seconds`` guarantee the gate can never trap the
    agent forever — on exhaustion it releases and the turn ends normally.

    Disabled by default (callers pass ``None``); behaviour is then
    byte-for-byte unchanged.
    """

    # Tools that must each have produced at least one successful, non-empty
    # result before END_TURN is allowed.
    required_tools: frozenset[str] = field(default_factory=frozenset)
    # When true, expose only still-required tools to the model until they have
    # succeeded.  This is intentionally narrower than the completion check:
    # it prevents an alternate implementation path from taking over before a
    # mandatory standard capability (for example native image generation) is
    # attempted.
    restrict_tools_until_required_succeed: bool = False
    # Artifact files that must exist and be non-empty before END_TURN is
    # allowed. Resolved relative to ``workspace_dir`` (absolute paths kept).
    required_artifacts: tuple[str, ...] = ()
    # At least one artifact matching any of these globs must be new or changed
    # compared with ``baseline_artifact_signatures`` before END_TURN is allowed.
    required_changed_artifact_globs: tuple[str, ...] = ()
    baseline_artifact_signatures: dict[str, tuple[int, int]] = field(
        default_factory=dict
    )
    # Changed artifacts with one of these suffixes additionally require a new
    # or updated JSON report whose top-level ``ok`` value is true.
    required_success_report_globs: tuple[str, ...] = ()
    success_report_artifact_suffixes: frozenset[str] = field(
        default_factory=frozenset
    )
    baseline_success_report_signatures: dict[str, tuple[int, int]] = field(
        default_factory=dict
    )
    # Safety valve: max number of continuation nudges the gate may inject.
    max_continuations: int = 3
    # Safety valve: release the gate once the run exceeds this many seconds.
    # ``None`` disables the time limit.
    deadline_seconds: float | None = None
    # Optional total tool-call budget for this gated run. ``run_agent_loop``
    # adopts it only when the caller did not provide a stricter explicit cap.
    max_tool_calls: int | None = None
    # Optional workflow-specific cap for external search. Presentation
    # authoring may activate the deep-research route, while still preserving
    # execution budget for scaffold, media, render, and QA work.
    web_search_total_limit: int | None = None
    # Tool names excluded from ``max_tool_calls`` for this workflow. Explicit
    # caller-provided budgets keep their original all-tools semantics unless
    # the caller also opts into exemptions through the gate.
    budget_exempt_tools: frozenset[str] = field(default_factory=frozenset)
    # Number of trailing budgeted calls reserved for deterministic completion
    # work. Core emits one evidence-backed nudge at ``max - reserve`` so the
    # model stops discovery and runs patch → validate → render → QA.
    completion_reserve_tool_calls: int = 0
    # A successful call to one of these tools is a valid resumable pause. The
    # completion gate allows END_TURN even when artifact gaps remain; the ACP
    # session retains the gate and resumes it after the user's next answer.
    pause_tools: frozenset[str] = field(default_factory=frozenset)
    # Optional filesystem-backed workflow checkpoint injected before each LLM
    # step.  Unlike conversational history, this state is re-derived from the
    # canonical artifacts, so a long-running model cannot accidentally regress
    # to an already-completed authoring stage after context compaction or
    # attention drift.
    workflow_checkpoint_kind: str | None = None
    # Research routing decided from the original presentation brief. ``deep``
    # requires research-synthesis artifacts before outline authoring; other
    # values remain advisory and do not add filesystem requirements.
    presentation_research_mode: str | None = None


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

PRESENTATION_DELIVERY_KEYWORDS: Final[tuple[str, ...]] = (
    "ppt",
    "pptx",
    "powerpoint",
    "演示文稿",
    "幻灯片",
    "slide deck",
    "slides",
)

_PRESENTATION_RESEARCH_SOURCE_FIRST_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:不要(?:联网|搜索)|不(?:要|用)搜索|仅(?:根据|基于)|只(?:根据|基于)|"
    r"基于(?:附件|文件|我提供)|根据(?:附件|文件)|我们的|我司|本公司|内部|"
    r"新员工|入职培训|no\s+(?:web|search)|without\s+(?:web|search)|"
    r"use\s+only\s+(?:the\s+)?(?:provided|attached))",
    re.IGNORECASE,
)
_PRESENTATION_RESEARCH_CREATIVE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:创意(?:视觉|插画|海报)?|插画|海报|氛围感|想象式|艺术化|视觉故事|"
    r"image[- ]rich|illustration|poster|purely\s+visual|atmospheric)",
    re.IGNORECASE,
)
_PRESENTATION_PAGE_PLAN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:第\s*\d+\s*页|slide\s*\d+\s*[:：.-])",
    re.IGNORECASE,
)
_PRESENTATION_OUTLINE_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"(?<!不要)(?<!别)(?<!不)(?:只|仅)(?:要|需要|需|输出|生成)?"
    r"(?:一份)?(?:ppt\s*)?(?:大纲|内容方案)(?:即可|就好|就可以)?"
    r"|(?:不要|无需|不需要)(?:生成|制作|渲染)(?:最终)?"
    r"(?:页面|幻灯片|html|pptx?)(?:文件)?(?=[，。；;.!?\s]|$)"
    r"|\b(?:outline\s+only|only\s+(?:need|want|create|provide)\s+"
    r"(?:an?\s+)?outline|do\s+not\s+(?:generate|create|render)\s+"
    r"(?:slides?|pages?|html))\b"
    r")",
    re.IGNORECASE,
)


def _presentation_research_mode(user_text: str) -> str:
    """Classify whether a presentation brief needs the deep-research checkpoint."""
    text = user_text.strip()
    if _PRESENTATION_RESEARCH_SOURCE_FIRST_RE.search(text):
        return "source_first"
    if _PRESENTATION_RESEARCH_CREATIVE_RE.search(text):
        return "creative"
    if len(_PRESENTATION_PAGE_PLAN_RE.findall(text)) >= 2:
        return "content_ready"
    substantive_lines = [line.strip() for line in text.splitlines() if line.strip()]
    bullet_lines = [
        line for line in substantive_lines
        if re.match(r"^(?:[-*•]|\d+[.、)])\s*", line)
    ]
    if len(bullet_lines) >= 3:
        return "content_ready"
    topic = re.sub(
        r"(?:做|制作|生成|创建|输出|导出|帮我|请|一份|一个|可编辑|"
        r"pptx?|powerpoint|演示文稿|幻灯片|slide\s*deck|slides?|"
        r"\d+\s*页|\d+\s*[x×]\s*\d+)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"[\s，。；;:：,.!?！？()（）]+", "", topic)
    if len(topic) < 4:
        return "auto"
    if len(substantive_lines) <= 2 and len(text) <= 400:
        return "deep"
    return "auto"

COMPLETION_GATE_PATTERNS: Final[
    tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
] = (
    (
        PRESENTATION_DELIVERY_KEYWORDS,
        (
            f"{OUTPUT_SUBDIR}/**/*.html",
            f"{OUTPUT_SUBDIR}/**/*.htm",
            f"{OUTPUT_SUBDIR}/**/*.pptx",
            f"{OUTPUT_SUBDIR}/**/*.ppt",
        ),
    ),
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

EXPLICIT_PPTX_DELIVERY_KEYWORDS: Final[tuple[str, ...]] = (
    "pptx",
    ".pptx",
)

IMAGE_ARTIFACT_GLOBS: Final[tuple[str, ...]] = (
    f"{OUTPUT_SUBDIR}/**/*.png",
    f"{OUTPUT_SUBDIR}/**/*.jpg",
    f"{OUTPUT_SUBDIR}/**/*.jpeg",
    f"{OUTPUT_SUBDIR}/**/*.webp",
)

NATIVE_IMAGE_ACTION_KEYWORDS: Final[tuple[str, ...]] = (
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

NATIVE_IMAGE_OUTPUT_KEYWORDS: Final[tuple[str, ...]] = (
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

NON_NATIVE_IMAGE_DELIVERY_KEYWORDS: Final[tuple[str, ...]] = (
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

NEGATED_FORMAT_CLAUSE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:不要|不用|禁止|避免|无需|不能|不可|别|"
    r"\b(?:do\s+not|don't|without|avoid|never|no)\b)"
    r"[^，。；;.!?\n]*",
    re.IGNORECASE,
)


def _strip_negated_format_clauses(text: str) -> str:
    return NEGATED_FORMAT_CLAUSE_RE.sub(" ", text)


def _is_native_image_generation_request(text: str, positive_format_text: str) -> bool:
    has_action = any(keyword in text for keyword in NATIVE_IMAGE_ACTION_KEYWORDS)
    has_image_output = any(
        keyword in text for keyword in NATIVE_IMAGE_OUTPUT_KEYWORDS
    )
    has_non_native_delivery = any(
        keyword in positive_format_text
        for keyword in NON_NATIVE_IMAGE_DELIVERY_KEYWORDS
    )
    return has_action and has_image_output and not has_non_native_delivery


def build_auto_completion_gate(
    user_text: str,
    workspace_dir: str | Path,
) -> CompletionGate | None:
    """Create a delivery-artifact gate when the prompt clearly asks for one."""
    text = user_text.strip().lower()
    if not text or not any(keyword in text for keyword in DELIVERABLE_INTENT_KEYWORDS):
        return None

    positive_format_text = _strip_negated_format_clauses(text)
    presentation_outline_only = bool(_PRESENTATION_OUTLINE_ONLY_RE.search(text))
    presentation_delivery = any(
        keyword in positive_format_text
        for keyword in PRESENTATION_DELIVERY_KEYWORDS
    )
    native_image_generation = _is_native_image_generation_request(
        text,
        positive_format_text,
    )
    explicit_pptx = (
        not presentation_outline_only
        and any(
            keyword in positive_format_text
            for keyword in EXPLICIT_PPTX_DELIVERY_KEYWORDS
        )
    )
    if native_image_generation:
        patterns: list[str] = list(IMAGE_ARTIFACT_GLOBS)
    else:
        patterns = [f"{OUTPUT_SUBDIR}/**/*.pptx"] if explicit_pptx else []
    if (
        not native_image_generation
        and not explicit_pptx
        and presentation_delivery
        and not presentation_outline_only
    ):
        patterns.extend(COMPLETION_GATE_PATTERNS[0][1])
    elif not native_image_generation and not explicit_pptx and not presentation_delivery:
        for keywords, artifact_patterns in COMPLETION_GATE_PATTERNS:
            if any(keyword in positive_format_text for keyword in keywords):
                patterns.extend(artifact_patterns)

    if not patterns:
        return None

    deduped_patterns = tuple(dict.fromkeys(patterns))
    workspace = str(workspace_dir)
    presentation_html = (
        not native_image_generation
        and not explicit_pptx
        and presentation_delivery
        and not presentation_outline_only
    )
    presentation_research_mode = (
        _presentation_research_mode(user_text) if presentation_html else None
    )
    success_report_globs = (
        (
            f"{OUTPUT_SUBDIR}/**/qa/outline_check.json",
            f"{OUTPUT_SUBDIR}/**/qa/deck_contract.json",
            f"{OUTPUT_SUBDIR}/**/qa/deck_spec.json",
            f"{OUTPUT_SUBDIR}/**/qa/truth_check.json",
            f"{OUTPUT_SUBDIR}/**/qa/image_manifest.json",
            f"{OUTPUT_SUBDIR}/**/qa/html_self_check.json",
            f"{OUTPUT_SUBDIR}/**/qa/runtime_probe.json",
        )
        if presentation_html
        else ()
    )
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
        required_success_report_globs=success_report_globs,
        success_report_artifact_suffixes=(
            frozenset({".html", ".htm"}) if presentation_html else frozenset()
        ),
        baseline_success_report_signatures=artifact_signatures_for_globs(
            success_report_globs,
            workspace,
        ),
        max_continuations=3,
        deadline_seconds=900.0,
        # Count artifact work, not UI bookkeeping. A 10-15 slide image-rich
        # deck gets a bounded 64-call substantive budget, with the last ten
        # calls explicitly reserved for patch/validation/render/QA closure.
        max_tool_calls=(80 if presentation_research_mode == "deep" else 64)
        if presentation_html
        else None,
        # Do not impose a PPT-specific search cap. The normal runtime safety
        # limit still applies, while research-synthesis decides when the
        # coarse-to-fine evidence coverage is sufficient.
        web_search_total_limit=None,
        budget_exempt_tools=(
            PRESENTATION_BUDGET_EXEMPT_TOOLS
            if presentation_html
            else frozenset()
        ),
        completion_reserve_tool_calls=10 if presentation_html else 0,
        pause_tools=(
            frozenset({"request_user_input"})
            if presentation_html
            else frozenset()
        ),
        workflow_checkpoint_kind=(
            "controlled_presentation" if presentation_html else None
        ),
        presentation_research_mode=presentation_research_mode,
    )


CONTROLLED_PRESENTATION_CHECKPOINT_MARKER: Final = (
    "CONTROLLED_PRESENTATION_STAGE="
)

_SCAFFOLD_PLACEHOLDERS: Final[tuple[str, ...]] = (
    "输入演示标题",
    "输入页面标题",
    "输入数据结论",
    "输入流程标题",
    "在这里写下最需要被记住的结论",
    "品牌项目 A（待补充）",
)

_CONTROLLED_PRESENTATION_REPORTS: Final[tuple[str, ...]] = (
    "outline_check.json",
    "deck_contract.json",
    "deck_spec.json",
    "truth_check.json",
    "image_manifest.json",
    "html_self_check.json",
    "runtime_probe.json",
)


def _newest_file(paths: list[Path]) -> Path | None:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime_ns)


def _deck_has_scaffold_placeholders(deck_path: Path) -> bool:
    try:
        text = deck_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(placeholder in text for placeholder in _SCAFFOLD_PLACEHOLDERS)


def _report_is_ok(report_path: Path) -> bool:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("ok") is True


def _report_state(
    report_path: Path,
    dependencies: tuple[Path, ...] = (),
) -> str:
    """Return missing, invalid, failed, ok, or stale_* for one QA report."""
    try:
        text = report_path.read_text(encoding="utf-8")
    except OSError:
        return "missing"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "invalid"
    if not isinstance(payload, dict):
        state = "invalid"
    else:
        state = "ok" if payload.get("ok") is True else "failed"
    try:
        report_mtime = report_path.stat().st_mtime_ns
        if any(
            dependency.is_file()
            and dependency.stat().st_mtime_ns > report_mtime
            for dependency in dependencies
        ):
            return f"stale_{state}"
    except OSError:
        pass
    return state


def _report_warning_count(report_path: Path) -> int:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        return len(warnings)
    if isinstance(warnings, int) and warnings > 0:
        return warnings
    return 0


def _presentation_research_artifacts(workspace_dir: str | Path) -> tuple[bool, tuple[Path, ...]]:
    """Return whether a fresh validated deep-research handoff is complete."""
    workspace_root = Path(workspace_dir)
    # Presentation tools execute from the artifact root (``output/``), so the
    # canonical research handoff is ``output/research``.  Older sessions and
    # direct callers may still have written ``research`` beside ``output``;
    # retain that location as a read-only compatibility fallback.
    research_roots = (
        workspace_root / OUTPUT_SUBDIR / "research",
        workspace_root / "research",
    )
    research_root = next(
        (candidate for candidate in research_roots if candidate.is_dir()),
        None,
    )
    if research_root is None:
        return (False, ())

    def non_empty(paths: Iterable[Path]) -> list[Path]:
        found = []
        for candidate in paths:
            try:
                if candidate.is_file() and candidate.stat().st_size > 0:
                    found.append(candidate)
            except OSError:
                continue
        return sorted(found)

    observed = non_empty(research_root.rglob("*.md"))
    report_paths = non_empty(research_root.rglob("*_research_check.json"))
    for report_path in sorted(
        report_paths,
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    ):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            continue
        if payload.get("validator") != "research-synthesis":
            continue
        route = payload.get("route")
        topic = payload.get("topic")
        min_dimensions = payload.get("min_dimensions")
        dimension_count = payload.get("dimension_count")
        if (
            route not in {"A", "B"}
            or not isinstance(topic, str)
            or not topic.strip()
            or not isinstance(min_dimensions, int)
            or min_dimensions < 3
            or not isinstance(dimension_count, int)
            or dimension_count < min_dimensions
        ):
            continue
        dimensions = non_empty(research_root.glob(f"{topic}_dim*.md"))
        wide = non_empty(research_root.glob(f"{topic}_wide*.md"))
        cross_verification = non_empty(
            [research_root / f"{topic}_cross_verification.md"]
        )
        insights = non_empty([research_root / f"{topic}_insight.md"])
        if (
            len(dimensions) < min_dimensions
            or (route == "A" and not wide)
            or not cross_verification
            or not insights
        ):
            continue
        handoff_files = tuple(
            dict.fromkeys(
                [*wide, *dimensions, *cross_verification, *insights, report_path]
            )
        )
        try:
            report_mtime = report_path.stat().st_mtime_ns
            if any(path.stat().st_mtime_ns > report_mtime for path in handoff_files[:-1]):
                continue
        except OSError:
            continue
        return (True, handoff_files)
    return (False, tuple(dict.fromkeys([*observed, *report_paths])))


def _manifest_generation_progress(
    manifest_path: Path,
    artifact_root: Path,
) -> tuple[int, int, int, tuple[str, ...]]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return (0, 0, 0, ())
    image_plan = payload.get("image_plan") if isinstance(payload, dict) else None
    if not isinstance(image_plan, list):
        return (0, 0, 0, ())
    expected = 0
    ready = 0
    status_ready = 0
    ready_paths: list[str] = []
    for entry in image_plan:
        if not isinstance(entry, dict):
            continue
        decision = entry.get("decision")
        if decision not in {"generate", "use_existing"}:
            continue
        if decision == "generate":
            expected += 1
        output_path = entry.get("output_path")
        if not isinstance(output_path, str) or not output_path.strip():
            continue
        path = artifact_root / output_path
        try:
            if path.is_file() and path.stat().st_size > 0:
                ready_paths.append(output_path.strip())
                if decision != "generate":
                    continue
                ready += 1
                status = str(entry.get("status") or "").strip().lower()
                if status in {
                    "generated",
                    "ready",
                    "complete",
                    "completed",
                    "reused",
                    "fixed",
                }:
                    status_ready += 1
        except OSError:
            continue
    return (ready, expected, status_ready, tuple(ready_paths))


def _missing_artifact_references(
    artifact_path: Path,
    references: tuple[str, ...] | list[str],
) -> list[str]:
    if not references:
        return []
    try:
        text = artifact_path.read_text(encoding="utf-8")
    except OSError:
        return list(references)
    return [reference for reference in references if reference not in text]


def _json_field_shape(value: object) -> object:
    """Return a compact JSON-compatible field shape without scaffold prose."""
    if isinstance(value, dict):
        return {str(key): _json_field_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_field_shape(value[0])] if value else []
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return 0
    if value is None:
        return None
    return "<string>"


def _outline_title_prop_path(layout_id: object, props: dict[str, object]) -> str | None:
    """Return the visible heading prop that must preserve the outline title."""
    if layout_id == "statement-focus-v1" and "statement" in props:
        return "statement"
    if "title" in props:
        return "title"
    return None


def _numeric_literals(*values: object) -> list[str]:
    """Return digit-bearing literals explicitly present in page source text."""
    source = json.dumps(values, ensure_ascii=False)
    return list(dict.fromkeys(re.findall(r"\d+(?:[.,]\d+)?(?:[%％])?", source)))


_MISSING_PRIVATE_FACT_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:未提供|未给出|待补充|待确认|缺失|未知|"
    r"not\s+provided|not\s+supplied|missing|unknown|tbd)",
    re.IGNORECASE,
)


def _missing_fact_evidence(value: object) -> list[str]:
    """Return exact outline evidence that discloses unavailable private facts."""
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str)
        and item.strip()
        and _MISSING_PRIVATE_FACT_RE.search(item)
    ]


def _content_patch_input(
    outline_path: Path | None,
    deck_path: Path,
    generated_paths: tuple[str, ...],
) -> str | None:
    """Build the complete compact input needed for one all-slide content patch."""
    if outline_path is None:
        return None
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    outline_slides = outline.get("slides") if isinstance(outline, dict) else None
    deck_slides = deck.get("slides") if isinstance(deck, dict) else None
    if not isinstance(outline_slides, list) or not isinstance(deck_slides, list):
        return None
    source_mode = str(outline.get("source_mode") or "").strip().lower()
    user_provided_source = source_mode == "user_provided"

    media_bindings: list[dict[str, object]] = []
    manifest_path = deck_path.parent / "assets" / "generated" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = None
    image_plan = manifest.get("image_plan") if isinstance(manifest, dict) else None
    if isinstance(image_plan, list):
        ready_path_set = set(generated_paths)
        media_bindings = [
            {
                "slide_id": entry.get("slide_id"),
                "prop_path": entry.get("prop_path"),
                "path": entry.get("output_path"),
                "origin": "uploaded"
                if entry.get("decision") == "use_existing"
                else "generated",
                "alt_policy": (
                    "Describe supplied asset accurately"
                    if entry.get("decision") == "use_existing"
                    else "Label product/project concepts as AI concept visuals, not documentary screenshots"
                ),
            }
            for entry in image_plan
            if isinstance(entry, dict)
            and entry.get("output_path") in ready_path_set
        ]

    pages: list[dict[str, object]] = []
    for index, deck_slide in enumerate(deck_slides):
        if not isinstance(deck_slide, dict):
            continue
        source_page = deck_slide.get("source_outline_page")
        outline_index = source_page - 1 if isinstance(source_page, int) else index
        if not (0 <= outline_index < len(outline_slides)):
            return None
        outline_slide = outline_slides[outline_index]
        if not isinstance(outline_slide, dict):
            return None
        props = deck_slide.get("props")
        props_dict = props if isinstance(props, dict) else {}
        missing_fact_evidence = _missing_fact_evidence(
            outline_slide.get("evidence")
        )
        structural_numeric_literals = (
            [str(len(deck_slides))] if outline_index == 0 else []
        )
        pages.append(
            {
                "slide_id": deck_slide.get("id") or f"slide-{index + 1:02d}",
                "layout_id": deck_slide.get("layout_id"),
                "source_outline_page": outline_index + 1,
                "title": outline_slide.get("title"),
                "title_prop_path": _outline_title_prop_path(
                    deck_slide.get("layout_id"),
                    props_dict,
                ),
                "message": outline_slide.get("message"),
                "bullets": outline_slide.get("bullets"),
                "evidence": outline_slide.get("evidence"),
                "disclosure_required": bool(missing_fact_evidence),
                "disclosure_evidence": missing_fact_evidence,
                # Public research remains bound to its evidence ledger. In a
                # user-provided outline, exact quantities in the page copy came
                # directly from the user and are valid even without URL evidence.
                "allowed_numeric_literals": _numeric_literals(
                    outline_slide.get("evidence"),
                    outline_slide.get("message") if user_provided_source else None,
                    outline_slide.get("bullets") if user_provided_source else None,
                ),
                # The page count is a structural deck fact, not researched topic
                # evidence. It is safe only in cover metadata explicitly labelled
                # as a page/slide count.
                "structural_numeric_literals": structural_numeric_literals,
                "prop_shape": _json_field_shape(props_dict),
                "props_template": props_dict,
            }
        )
    if not pages:
        return None
    truth_contract = deck.get("truth_contract")
    compact_truth = None
    if isinstance(truth_contract, dict):
        compact_truth = {
            key: truth_contract.get(key)
            for key in ("source_facts", "research_facts", "assumptions")
            if isinstance(truth_contract.get(key), list)
        }
    return json.dumps(
        {
            "patch_format": (
                'Top level must be {"slides":{...}}. Nest every supplied '
                'slide_id under slides, for example '
                '{"slides":{"slide-01":{"props":{...}}}}; never put '
                'slide-01, slide-02, etc. at the top level.'
            ),
            "ready_media_paths": list(generated_paths),
            "ready_media_bindings": media_bindings,
            "truth_contract": compact_truth,
            "pages": pages,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _scaffold_input(outline_path: Path) -> str | None:
    """Return registered ids plus compact page intent for one scaffold call."""
    manifest_path = (
        Path(__file__).resolve().parent
        / "skills"
        / "document-skills"
        / "pptx"
        / "layouts"
        / "manifest.json"
    )
    try:
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    outline_slides = outline.get("slides") if isinstance(outline, dict) else None
    themes = manifest.get("themes") if isinstance(manifest, dict) else None
    layouts = manifest.get("layouts") if isinstance(manifest, dict) else None
    if (
        not isinstance(outline_slides, list)
        or not isinstance(themes, list)
        or not isinstance(layouts, list)
    ):
        return None

    theme_ids = [
        theme.get("id")
        for theme in themes
        if isinstance(theme, dict) and isinstance(theme.get("id"), str)
    ]
    registered_layouts = [
        {
            "id": layout.get("id"),
            "label": layout.get("label"),
            "roles": layout.get("roles"),
            "content_shape": layout.get("contentShape"),
            "density": layout.get("density"),
        }
        for layout in layouts
        if isinstance(layout, dict) and isinstance(layout.get("id"), str)
    ]
    layout_ids = [layout["id"] for layout in registered_layouts]
    pages = [
        {
            "page": slide.get("page"),
            "title": slide.get("title"),
            "message": slide.get("message"),
            "layout_intent": slide.get("layout"),
            "visual_intent": slide.get("visual"),
            "evidence": slide.get("evidence"),
        }
        for slide in outline_slides
        if isinstance(slide, dict)
    ]
    if not theme_ids or not layout_ids or not pages:
        return None
    return json.dumps(
        {
            "default_theme_id": manifest.get("default_theme_id"),
            "registered_theme_ids": theme_ids,
            "registered_layout_ids": layout_ids,
            "registered_layouts": registered_layouts,
            "pages": pages,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _image_generation_input(
    manifest_path: Path,
    artifact_root: Path,
    outline_path: Path | None,
    deck_path: Path,
) -> str | None:
    """Return every missing planned image with enough context to generate it."""
    layout_manifest_path = (
        Path(__file__).resolve().parent
        / "skills"
        / "document-skills"
        / "pptx"
        / "layouts"
        / "manifest.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        layout_manifest = json.loads(layout_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or not isinstance(deck, dict):
        return None
    image_plan = manifest.get("image_plan")
    if not isinstance(image_plan, list):
        return None

    outline_pages: dict[int, dict[str, object]] = {}
    if outline_path is not None:
        try:
            outline = json.loads(outline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            outline = None
        if isinstance(outline, dict) and isinstance(outline.get("slides"), list):
            outline_pages = {
                slide.get("page"): slide
                for slide in outline["slides"]
                if isinstance(slide, dict) and isinstance(slide.get("page"), int)
            }

    layouts = layout_manifest.get("layouts") if isinstance(layout_manifest, dict) else []
    layout_by_id = {
        layout.get("id"): layout
        for layout in layouts or []
        if isinstance(layout, dict) and isinstance(layout.get("id"), str)
    }
    themes = layout_manifest.get("themes") if isinstance(layout_manifest, dict) else []
    theme = next(
        (
            item
            for item in themes or []
            if isinstance(item, dict) and item.get("id") == deck.get("theme_id")
        ),
        None,
    )

    pending: list[dict[str, object]] = []
    for entry in image_plan:
        if not isinstance(entry, dict) or entry.get("decision") != "generate":
            continue
        output_path = entry.get("output_path")
        if not isinstance(output_path, str) or not output_path.strip():
            continue
        try:
            if (artifact_root / output_path).is_file():
                continue
        except OSError:
            pass
        page = entry.get("slide")
        outline_slide = outline_pages.get(page) if isinstance(page, int) else None
        layout = layout_by_id.get(entry.get("layout_id"))
        preferred_ratio = None
        if isinstance(layout, dict):
            media_slots = layout.get("mediaSlots")
            slots = media_slots.get("slots") if isinstance(media_slots, dict) else None
            if isinstance(slots, list):
                slot = next(
                    (
                        item
                        for item in slots
                        if isinstance(item, dict) and item.get("id") == entry.get("slot")
                    ),
                    None,
                )
                if isinstance(slot, dict):
                    preferred_ratio = slot.get("preferredRatio")
        pending.append(
            {
                "slide": page,
                "slide_id": entry.get("slide_id"),
                "layout_id": entry.get("layout_id"),
                "slot": entry.get("slot"),
                "prop_path": entry.get("prop_path"),
                "output_path": output_path.strip(),
                "preferred_ratio": preferred_ratio,
                "existing_prompt": entry.get("prompt"),
                "title": outline_slide.get("title") if outline_slide else None,
                "message": outline_slide.get("message") if outline_slide else None,
                "visual_intent": outline_slide.get("visual") if outline_slide else None,
            }
        )
    if not pending:
        return None
    return json.dumps(
        {
            "deck_title": deck.get("title"),
            "theme_id": deck.get("theme_id"),
            "theme_style": theme.get("style") if isinstance(theme, dict) else None,
            "theme_palette": theme.get("palette") if isinstance(theme, dict) else None,
            "watermark": False,
            "negative_prompt": "embedded text, watermark, logo, blurry output",
            "entries": pending,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _qa_repair_input(
    report_path: Path,
    deck_path: Path,
    outline_path: Path | None,
) -> str | None:
    """Return fresh report issues with the exact affected slide context."""
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict) or not isinstance(deck, dict):
        return None
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = report.get("errors")
    issues = [issue for issue in raw_issues or [] if isinstance(issue, str)]
    if not issues:
        return None

    affected_ids = {
        match.group(1)
        for issue in issues
        for match in re.finditer(r"slides\.(slide-[A-Za-z0-9_-]+)", issue)
    }
    deck_slides = deck.get("slides")
    if not affected_ids or not isinstance(deck_slides, list):
        return None

    outline_slides: list[object] = []
    if outline_path is not None:
        try:
            outline = json.loads(outline_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            outline = None
        if isinstance(outline, dict) and isinstance(outline.get("slides"), list):
            outline_slides = outline["slides"]

    affected_slides: list[dict[str, object]] = []
    for index, slide in enumerate(deck_slides):
        if not isinstance(slide, dict) or slide.get("id") not in affected_ids:
            continue
        source_page = slide.get("source_outline_page")
        outline_index = source_page - 1 if isinstance(source_page, int) else index
        outline_slide = (
            outline_slides[outline_index]
            if 0 <= outline_index < len(outline_slides)
            and isinstance(outline_slides[outline_index], dict)
            else None
        )
        affected_slides.append(
            {
                "slide_id": slide.get("id"),
                "source_outline_page": outline_index + 1,
                "current_props": slide.get("props"),
                "protected_title_prop_path": _outline_title_prop_path(
                    slide.get("layout_id"),
                    (
                        slide.get("props")
                        if isinstance(slide.get("props"), dict)
                        else {}
                    ),
                ),
                "outline": (
                    {
                        "title": outline_slide.get("title"),
                        "message": outline_slide.get("message"),
                        "bullets": outline_slide.get("bullets"),
                        "evidence": outline_slide.get("evidence"),
                    }
                    if outline_slide is not None
                    else None
                ),
            }
        )
    if not affected_slides:
        return None

    truth_contract = deck.get("truth_contract")
    compact_truth = None
    if isinstance(truth_contract, dict):
        compact_truth = {
            key: truth_contract.get(key)
            for key in ("source_facts", "research_facts", "assumptions")
            if isinstance(truth_contract.get(key), list)
        }
    return json.dumps(
        {
            "report": report_path.name,
            "issues": issues,
            "affected_slides": affected_slides,
            "truth_contract": compact_truth,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _outline_repair_input(
    report_path: Path,
    outline_path: Path,
    research_files: tuple[Path, ...] = (),
) -> str | None:
    """Return one self-contained input for repairing a failed outline.

    A failing validator writes the useful issue list to JSON while the bash tool
    itself commonly reports only exit code 1.  Embedding both that list and the
    current outline prevents repeated report/file/reference reads and gives the
    model one exact mutation target.
    """
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(report, dict) or not isinstance(outline, dict):
        return None
    raw_issues = report.get("issues")
    if not isinstance(raw_issues, list):
        raw_issues = report.get("errors")
    issues = [issue for issue in raw_issues or [] if isinstance(issue, str)]
    if not issues:
        return None
    # Match the same conservative URL surface used by the runtime provenance
    # ledger.  In particular, do not absorb Markdown closing delimiters into a
    # URL, otherwise a valid handoff link can be mislabeled as unsupported.
    url_pattern = re.compile(
        r"https?://[^\s<>\"'\]\[{}()|]+",
        re.IGNORECASE,
    )
    allowed_research_urls: set[str] = set()
    for research_file in research_files:
        if research_file.suffix.casefold() != ".md":
            continue
        try:
            research_text = research_file.read_text(encoding="utf-8")
        except OSError:
            continue
        allowed_research_urls.update(
            match.rstrip(".,;:!?，。；：！？")
            for match in url_pattern.findall(research_text)
        )
    current_outline_urls = {
        match.rstrip(".,;:!?，。；：！？")
        for match in url_pattern.findall(
            json.dumps(outline, ensure_ascii=False, separators=(",", ":"))
        )
    }
    return json.dumps(
        {
            "report": report_path.name,
            "issues": issues,
            "allowed_research_urls": sorted(allowed_research_urls),
            "unsupported_evidence_urls": sorted(
                current_outline_urls - allowed_research_urls
            ),
            "current_outline": outline,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def completion_gate_progress_text(
    gate: CompletionGate,
    workspace_dir: str | None,
) -> str | None:
    """Return an authoritative next-stage checkpoint for controlled decks.

    The checkpoint intentionally uses only filesystem evidence. It is safe to
    recompute before every model request; core keeps one refreshed copy as the
    latest instruction while emitting a new checkpoint event only when the
    filesystem-backed stage changes.
    """
    if (
        gate.workflow_checkpoint_kind != "controlled_presentation"
        or not workspace_dir
    ):
        return None

    output_root = Path(workspace_dir) / OUTPUT_SUBDIR
    research_required = gate.presentation_research_mode == "deep"
    research_ready, research_files = _presentation_research_artifacts(workspace_dir)
    outline_path = _newest_file(list(output_root.rglob("outline.json")))
    deck_path = _newest_file(list(output_root.rglob("deck.json")))
    html_path = _newest_file(
        [
            path
            for path in output_root.rglob("*.html")
            if "qa" not in path.parts
        ]
    )
    try:
        html_current = html_path is not None and (
            deck_path is None
            or html_path.stat().st_mtime_ns >= deck_path.stat().st_mtime_ns
        )
    except OSError:
        html_current = False
    artifact_root = deck_path.parent if deck_path is not None else (
        html_path.parent if html_path is not None else (
            outline_path.parent if outline_path is not None else output_root
        )
    )
    patch_path = artifact_root / "deck.patch.json"
    manifest_path = artifact_root / "assets" / "generated" / "manifest.json"
    (
        generated_ready,
        generated_expected,
        generated_status_ready,
        generated_paths,
    ) = _manifest_generation_progress(
        manifest_path,
        artifact_root,
    )
    report_dir = artifact_root / "qa"
    validate_outline_command = _controlled_pptx_command(
        "validate_outline.js",
        "outline.json --report qa/outline_check.json",
    )
    apply_patch_command = _controlled_pptx_command(
        "apply_deck_patch.js",
        "deck.json deck.patch.json",
    )
    finalize_command = _controlled_pptx_command(
        "finalize_controlled_deck.js",
        "deck.json --out index.html",
    )
    sync_image_status_command = _controlled_pptx_command(
        "sync_image_manifest_status.js",
        "assets/generated/manifest.json",
    )
    generated_files = tuple(artifact_root / path for path in generated_paths)
    report_dependencies: dict[str, tuple[Path, ...]] = {
        "outline_check.json": tuple(
            path
            for path in (
                outline_path,
                *(research_files if research_required else ()),
            )
            if path
        ),
        "deck_contract.json": (),
        "deck_spec.json": tuple(
            path for path in (deck_path, outline_path) if path
        ),
        "truth_check.json": tuple(path for path in (deck_path,) if path),
        "image_manifest.json": tuple(
            path
            for path in (deck_path, manifest_path, *generated_files)
            if path is not None and path.is_file()
        ),
        "html_self_check.json": tuple(
            path for path in (html_path, deck_path) if path
        ),
        "runtime_probe.json": tuple(
            path for path in (html_path, deck_path) if path
        ),
    }
    report_states = {
        name: _report_state(
            report_dir / name,
            report_dependencies.get(name, ()),
        )
        for name in _CONTROLLED_PRESENTATION_REPORTS
    }
    report_status = {
        name: state == "ok" for name, state in report_states.items()
    }
    qa_ready = sum(report_status.values())
    qa_warnings = sum(
        _report_warning_count(report_dir / name)
        for name in _CONTROLLED_PRESENTATION_REPORTS
    )

    outline_report_path = report_dir / "outline_check.json"
    outline_repair_input = (
        _outline_repair_input(
            outline_report_path,
            outline_path,
            research_files if research_required else (),
        )
        if outline_path is not None
        and report_states["outline_check.json"] == "failed"
        else None
    )
    if (
        research_required
        and not research_ready
        and deck_path is None
        and html_path is None
    ):
        stage = "research"
        next_action = (
            "This short factual presentation brief requires the preloaded "
            "research-synthesis workflow before outline authoring. Choose Route A "
            "for a broad landscape or Route B for a bounded topic, run the skill's "
            "coarse-to-fine searches, and preserve the full useful search evidence "
            "under research/. Do not replace that workflow with an ad-hoc four-query "
            "scan. Consume each result set before the next batch; every later query "
            "must name a still-uncovered slide-relevant dimension, conflict, or "
            "first-party source instead of lightly rephrasing an already-run "
            "entity/fact query. An empty AuthLevel or site:-filtered result is not "
            "permission to repeat the same intent without the filter. For a known "
            "exact URL, use an actually available direct browser tool; in officev3 "
            "use standalone Playwright MCP rather than browser-gateway "
            "source_preference:playwright, or use gateway auto/browser_connector. "
            "Do not create or validate outline.json yet. The checkpoint "
            "advances only after research/ contains at least three distinct "
            "dimension files, the route's cross-verification and insight files, "
            "and a fresh successful research/qa/*_research_check.json written by "
            "validate_research_artifacts.py --report. Route A must also include "
            "wide exploration. If an early "
            "outline already exists, preserve it; update it from the completed "
            "research in the next stage instead of deleting or duplicating it."
        )
    elif (deck_path is not None or html_path is not None) and outline_path is None:
        stage = "outline_backfill"
        next_action = (
            "The existing deck predates its required narrative provenance. Do not "
            "recreate or rewrite deck.json/index.html. Derive one outline.json from "
            "the existing ordered slides and their evidence, then run `"
            f"{validate_outline_command}`. This is a provenance backfill, not a "
            "new authoring pass."
        )
    elif (
        (deck_path is not None or html_path is not None)
        and outline_repair_input is not None
    ):
        stage = "outline_repair"
        next_action = (
            "REPAIR_INPUT below contains the complete current outline and the fresh "
            "validator issues. Do not reread outline.json, the report, outline.md, or "
            "run another command. Your very next tool call must write one corrected "
            "outline.json, preserving supported content and changing only what the "
            "issues require. Use canonical top-level keys deck_goal, audience, "
            "source_mode, storyline, slides and canonical per-slide keys page, title, "
            "message, bullets, layout, visual, evidence. Do not recreate or rewrite "
            "the existing deck or HTML. For public research, evidence may use only "
            "allowed_research_urls from REPAIR_INPUT; remove or replace every listed "
            "unsupported_evidence_url without searching again. The refreshed "
            "filesystem checkpoint will "
            "validate the repaired outline next."
        )
    elif (
        (deck_path is not None or html_path is not None)
        and report_states["outline_check.json"] != "ok"
    ):
        stage = "outline_qa"
        next_action = (
            "Validate the existing outline.json with `"
            f"{validate_outline_command}` and repair only reported outline issues. Do not "
            "recreate or rewrite the existing deck or HTML."
        )
    elif html_path is not None and html_current:
        missing_reports = [
            name for name, ok in report_status.items() if not ok
        ]
        if not missing_reports:
            stage = "complete"
            next_action = (
                "All required QA reports are ok. Stop calling tools and return "
                "the editable HTML deliverable to the user. "
                f"The reports contain {qa_warnings} warning(s); state that count "
                "as pass-with-warnings in Limitations and do not call the run "
                "clean, all-green, or warning-free when the count is non-zero."
            )
        else:
            stage = "qa"
            next_action = (
                "Keep the existing HTML and run or repair only the missing/failed "
                f"QA checks: {', '.join(missing_reports)}. Do not restart authoring."
            )
    elif deck_path is None:
        if outline_path is None:
            stage = "outline"
            next_action = (
                (
                    "Research QA is complete. Do not call web_search or any browser "
                    "tool again, do not reread the research QA report or outline.md, "
                    "and do not list/check the filesystem. If the handoff contents "
                    "are not already present in the current model context, read only "
                    "the completed Markdown handoff files named in RESEARCH_INPUT in "
                    "one parallel batch; otherwise skip reading. Then your very next "
                    "tool call must write outline.json. "
                    if research_required and research_ready
                    else ""
                )
                + "Create exactly one concise outline.json before theme/layout "
                "selection using the canonical keys. Top level: deck_goal, "
                "audience, source_mode, storyline, slides. Every slide: page, "
                "title, message, bullets, layout, visual, evidence; bullets and "
                "evidence are arrays (use [] when evidence is empty); audience "
                "and storyline may each be a non-empty string or a non-empty "
                "array of strings. Do not use "
                "aliases such as goal, slide_no, layout_intent, or visual_intent. "
                "Set source_mode=public_authoritative_research after public "
                "research, give every page one distinct message and 2-5 "
                "substantive bullets, and do not spend multiple pages repeating "
                "the same fact. On a public-research page, every Arabic-number "
                "literal used in its title, message, or bullets must also appear "
                "verbatim in that page's evidence array; evidence is the fact "
                "ledger, so remove decorative/structural numbers that are not "
                "content claims. Every non-empty public-research evidence item "
                "must include at least one evidence item per page, and every item "
                "must include the actual http(s) source URL used for that claim. "
                "Treat AuthLevel as a ranking hint, not proof of authority: when "
                "a first-party domain is known, use a site:-constrained query, "
                "discard SEO-looking/mirror/unrelated results, and never label a "
                "source FIFA/IOC/official unless the returned URL belongs to that "
                "institution. Runtime provenance binding rejects URLs not returned "
                "by successful search, supplied by the user, read successfully "
                "through a direct browser tool, or preserved in the fresh validated "
                "RESEARCH_INPUT handoff. If a site: query yields "
                "no matching host, do not invent the expected URL: successfully read "
                "a known exact first-party URL or call request_user_input once. This "
                "schema is complete: do not read outline.md "
                "again, inspect/list themes or layouts, load a visual-template "
                "skill, or list the empty output directory until outline_check is "
                "ok. Assumptions may describe disclosed illustrative metrics or "
                "scenarios only. Never assume a company/project name, financing "
                "round or stage, founding date, team member/history/size, client, "
                "award, or other private identity fact; use 待补充 for a required "
                "private field, ask once when it blocks the deck, or omit an "
                "optional gap. For a public-research deck, omit nonessential gaps "
                "instead of planning visible 待补充 fields. Run `"
                f"{validate_outline_command}`, fix any issues, and stop before "
                "scaffolding so the validated narrative becomes the next checkpoint."
            )
        elif outline_repair_input is not None:
            stage = "outline_repair"
            next_action = (
                "REPAIR_INPUT below contains the complete current outline and the "
                "fresh validator issues. Do not reread outline.json, the report, "
                "outline.md, or run another command. Your very next tool call must "
                "write one corrected outline.json, preserving supported content and "
                "changing only what the issues require. Use canonical top-level keys "
                "deck_goal, audience, source_mode, storyline, slides and canonical "
                "per-slide keys page, title, message, bullets, layout, visual, "
                "evidence. For public research, evidence may use only "
                "allowed_research_urls from REPAIR_INPUT; remove or replace every "
                "listed unsupported_evidence_url without searching again. The "
                "refreshed filesystem checkpoint will validate it next; "
                "do not select layouts or scaffold deck.json yet."
            )
        elif report_states["outline_check.json"] != "ok":
            stage = "outline_qa"
            next_action = (
                "Validate the existing outline.json with `"
                f"{validate_outline_command}` and repair only its reported issues. Do not "
                "select layouts or scaffold deck.json until outline_check is ok."
            )
        else:
            stage = "scaffold"
            next_action = (
                "Use the validated outline.json as the page-by-page source of truth. "
                "SCAFFOLD_INPUT below already contains every registered theme/layout "
                "id and every page intent. Do not read outline.json, inspect/list the "
                "registry, or invent an id. Your very next tool call must invoke "
                "inspect_deck_contract.js once to create deck.json and its image "
                "manifest, passing `--outline outline.json --out deck.json`. The "
                "ordered plan may repeat layout "
                "ids; semantic fidelity is more important than forced variety. A "
                "qualitative page must not use chart-* or kpi-grid-v1 unless its "
                "outline evidence contains real quantities. For source_mode=user_provided, "
                "exact quantities in that page's message/bullets are evidence even when "
                "the external-link evidence array is empty. Choose layouts that can "
                "express each page's evidence without unresolved public-research "
                "placeholders. SCAFFOLD_INPUT.registered_layouts contains compact "
                "selection semantics; use project-case-study-v1 only for an actual "
                "source-backed project/case with proof metrics, not merely as a "
                "generic image-plus-text page. Choose --image-mode auto unless the brief activates "
                "creative_image_mode. Pass every --fact as an exact contiguous copy "
                "from the user's source; use --research-fact only for completed "
                "research not already present in the bound public-research outline, "
                "and --assumption only with explicit user permission. The scaffold "
                "automatically imports public outline evidence and writes "
                "source_outline_page. Do not paraphrase facts, infer dates, or "
                "repeat discovery calls."
            )
    else:
        has_placeholders = _deck_has_scaffold_placeholders(deck_path)
        patch_exists = patch_path.is_file() and patch_path.stat().st_size > 0
        missing_deck_media = _missing_artifact_references(
            deck_path,
            generated_paths,
        )
        missing_patch_media = (
            _missing_artifact_references(patch_path, missing_deck_media)
            if patch_exists
            else missing_deck_media
        )
        patch_needs_apply = False
        if patch_exists:
            try:
                patch_needs_apply = (
                    patch_path.stat().st_mtime_ns > deck_path.stat().st_mtime_ns
                    or has_placeholders
                )
            except OSError:
                patch_needs_apply = has_placeholders

        if generated_expected and generated_ready < generated_expected:
            stage = "images"
            next_action = (
                "IMAGE_INPUT below is complete and authoritative; do not read/list "
                "the manifest, deck, outline, generated-assets directory, or theme. "
                "Your very next tool call(s) must be one parallel batch of "
                "generate_image calls for only its entries. Use each exact "
                "output_path, watermark=false, the supplied palette/style and page "
                "intent, and avoid embedded text/logos. Do not edit manifest.json "
                "after generation; the next filesystem checkpoint will run the "
                "deterministic status sync. Never regenerate an existing file."
            )
        elif generated_expected and generated_status_ready < generated_expected:
            stage = "image_status_sync"
            next_action = (
                "All planned image files now exist; do not list the generated-assets "
                "directory, regenerate them, or edit/read manifest.json manually. "
                f"Run exactly `{sync_image_status_command}` once. The deterministic helper "
                "marks every existing planned asset ready without replacing the "
                "manifest, then the filesystem checkpoint will advance to the "
                "single all-slide content patch."
            )
        elif missing_deck_media and not patch_exists:
            stage = "content_patch"
            next_action = (
                "PATCH_INPUT below is complete and authoritative. Your very next "
                "tool call must write one deck.patch.json for all slides; do not "
                "call read_file, execute_code, bash, inspect/list, or any discovery "
                "tool first. The patch envelope must be exactly top-level "
                "{\"slides\":{...}}: nest each supplied slide_id under slides and "
                "never put slide-01/slide-02 keys at the top level. Include every ready "
                "generated media path in its declared prop or background. Keep "
                "slide N on outline page N: preserve its exact outline title and "
                "content anchors. On a quantitative page keep every allowed numeric "
                "literal with its matching label; values may be split across KPI/chart "
                "fields, so do not duplicate a full source sentence in every cell. On "
                "a qualitative page keep at least one exact atomic message/bullet "
                "fragment. Put the exact title in each page's "
                "declared title_prop_path. A digit-bearing value may appear only when "
                "that exact literal is listed in the page's allowed_numeric_literals; "
                "The cover may additionally use structural_numeric_literals only in "
                "a meta field explicitly labelled as a page/slide count. "
                "Do not translate Chinese number words into new Arabic metrics. Do "
                "not swap page topics, reuse the "
                "same evidence as the main point on more than two slides, or fill a "
                "qualitative page with dummy chart/KPI values. Use only "
                "scaffolded source facts plus explicitly user-authorized, visibly "
                "disclosed assumptions in truth_contract.assumptions. When a page "
                "has disclosure_required=true, visibly include its supplied "
                "disclosure_evidence in a subtitle, source, or note; never turn a "
                "missing team/company/project/funding fact into positive copy. Use "
                "待补充 only for required private fields, otherwise describe the "
                "capability or requirement neutrally. For public "
                "research, omit an unsupported optional claim rather than exposing "
                "待补充. Keep the "
                "existing manifest image_plan array schema; "
                "never replace manifest.json or rewrite deck.json directly."
            )
        elif missing_deck_media and missing_patch_media:
            stage = "media_patch"
            next_action = (
                "Add the ready generated media paths missing from deck.patch.json "
                f"({', '.join(missing_patch_media)}) to their declared props or "
                f"backgrounds, then apply that patch with `{apply_patch_command}`. Never use "
                "an ad-hoc script to rewrite deck.json."
            )
        elif missing_deck_media:
            stage = "apply_patch"
            next_action = (
                "The existing deck.patch.json already references the ready generated "
                f"media. Apply it now with `{apply_patch_command}`."
            )
        elif patch_needs_apply:
            stage = "apply_patch"
            next_action = (
                f"Run `{apply_patch_command}` now. Its compiler normalizes aliases and strict "
                "source facts. Do not reread/rewrite either file first; revise the "
                "patch only if that command returns an actionable error."
            )
        elif has_placeholders and not patch_exists:
            stage = "content_patch"
            next_action = (
                "PATCH_INPUT below is complete and authoritative. Your very next "
                "tool call must write one deck.patch.json for all slides; do not "
                "call read_file, execute_code, bash, inspect/list, or any discovery "
                "tool first. The patch envelope must be exactly top-level "
                "{\"slides\":{...}}: nest each supplied slide_id under slides and "
                "never put slide-01/slide-02 keys at the top level. Keep slide N on "
                "outline page N: preserve its exact outline title and content anchors. "
                "On a quantitative page keep every allowed numeric literal with its "
                "matching label; values may be split across KPI/chart fields, so do "
                "not duplicate a full source sentence in every cell. On a qualitative "
                "page keep at least one exact atomic message/bullet fragment. Put the "
                "exact title in each page's declared "
                "title_prop_path. A digit-bearing value may appear only when that "
                "exact literal is listed in the page's allowed_numeric_literals. "
                "The cover may additionally use structural_numeric_literals only in "
                "a meta field explicitly labelled as a page/slide count. Do "
                "not translate Chinese number words into new Arabic metrics. Do not "
                "swap page topics, reuse the same "
                "evidence as the main point on more than two slides, or fill a "
                "qualitative page with dummy chart/KPI values. Before creating "
                "deck.patch.json, preserve the already-finalized manifest decisions; "
                "the images stage has already handled every planned generate item, so "
                "do not read or edit manifest.json here. Create one patch for all "
                "slides that includes every ready media path and "
                "uses scaffolded source facts plus explicitly user-authorized, visibly "
                "disclosed assumptions. When a page has disclosure_required=true, "
                "visibly include its supplied disclosure_evidence in a subtitle, "
                "source, or note; never promote a missing private fact to positive "
                "copy. For public research, omit an unsupported "
                "optional claim rather than exposing 待补充. Do not recreate deck.json."
            )
        elif report_states["deck_spec.json"] == "failed":
            stage = "deck_spec_repair"
            next_action = (
                "REPAIR_INPUT below contains the fresh report issues and exact "
                "affected slide context. Do not reread the report or deck. Create or "
                "revise a minimal "
                "deck.patch.json containing only the named slide prop/background "
                "paths. The filesystem checkpoint will apply it and then invoke the "
                "single deterministic finalizer; do not run a validator yourself. "
                "Do not reread absent later QA reports, do "
                "not rewrite the full deck, and never copy an "
                "INTERNAL_MODEL_HISTORY_PLACEHOLDER or omitted-tool-argument marker "
                "into a file."
            )
        elif report_states["deck_spec.json"] != "ok":
            stage = "finalize"
            next_action = (
                f"Run exactly one bash tool call: `{finalize_command}`. "
                "The deterministic helper refreshes stale/missing checks in order, "
                "stops at the first actionable failure, compiles HTML only after "
                "spec/truth/media pass, and then runs self-check plus runtime probe. "
                "Do not split it into individual validators or add another command."
            )
        elif report_states["truth_check.json"] == "failed":
            stage = "truth_repair"
            next_action = (
                "REPAIR_INPUT below contains the fresh truth issues, current affected "
                "props, outline evidence, and authorized fact buckets. Do not reread "
                "the report or deck. Write the smallest possible "
                "deck.patch.json keyed by the exact named slides.slide-XX.props "
                "paths. The filesystem checkpoint will apply it and invoke the "
                "single deterministic finalizer; do not run a validator yourself. "
                "Do not read or run deck_spec, image, HTML, "
                "or runtime reports until truth passes; those reports may not exist. "
                "The exact outline title at protected_title_prop_path is immutable; "
                "never replace it with or append 待补充 to satisfy truth. If that "
                "protected title is the only reported issue, treat it as a contract "
                "conflict and ask once for a genuinely missing required user/private "
                "fact rather than oscillating between truth and deck_spec. "
                "For public research, omit an unsupported optional claim instead of "
                "writing visible 待补充. "
                "Never rewrite the full patch/deck from model history and never "
                "write INTERNAL_MODEL_HISTORY_PLACEHOLDER or an omitted-tool-argument "
                "marker into a file."
            )
        elif report_states["truth_check.json"] != "ok":
            stage = "finalize"
            next_action = (
                f"Run exactly one bash tool call: `{finalize_command}`. "
                "It refreshes the ordered dependency chain and stops at the first "
                "actionable failure. Do not run a validator separately."
            )
        elif report_states["image_manifest.json"] == "failed":
            stage = "image_qa_repair"
            next_action = (
                "Read only qa/image_manifest.json and repair the named manifest or "
                "deck media paths with one focused edit. Then let the filesystem "
                "checkpoint invoke the single finalizer; do not run another "
                "validator directly, read absent HTML/runtime reports, or restart "
                "authoring."
            )
        else:
            stage = "finalize"
            next_action = (
                f"Run exactly one bash tool call: `{finalize_command}`. "
                "This is the only authorized finalization command: it validates "
                "spec, truth, and media in dependency order, renders editable HTML, "
                "then runs self-check and the 1440x900 runtime probe. It stops at "
                "the first actionable failure and suppresses large successful "
                "validator payloads. Do not split the chain, rerun discovery, or "
                "scaffold deck.json."
            )

    patch_input = (
        _content_patch_input(outline_path, deck_path, generated_paths)
        if stage == "content_patch" and deck_path is not None
        else None
    )
    scaffold_input = (
        _scaffold_input(outline_path)
        if stage == "scaffold" and outline_path is not None
        else None
    )
    image_input = (
        _image_generation_input(
            manifest_path,
            artifact_root,
            outline_path,
            deck_path,
        )
        if stage == "images" and deck_path is not None
        else None
    )
    repair_input = (
        outline_repair_input
        if stage == "outline_repair"
        else (
            _qa_repair_input(report_dir / "truth_check.json", deck_path, outline_path)
            if stage == "truth_repair" and deck_path is not None
            else (
                _qa_repair_input(report_dir / "deck_spec.json", deck_path, outline_path)
                if stage == "deck_spec_repair" and deck_path is not None
                else None
            )
        )
    )
    outline_label = str(outline_path.relative_to(Path(workspace_dir))) if outline_path else "missing"
    deck_label = str(deck_path.relative_to(Path(workspace_dir))) if deck_path else "missing"
    patch_label = str(patch_path.relative_to(Path(workspace_dir))) if patch_path.is_file() else "missing"
    html_label = str(html_path.relative_to(Path(workspace_dir))) if html_path else "missing"
    research_input = (
        json.dumps(
            {
                "mode": gate.presentation_research_mode,
                "ready": research_ready,
                "files": [
                    str(
                        path.relative_to(output_root)
                        if path.is_relative_to(output_root)
                        else path.relative_to(Path(workspace_dir))
                    )
                    for path in research_files
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if research_required
        else None
    )
    return (
        "Internal controlled-presentation checkpoint; filesystem evidence is "
        "authoritative and this instruction overrides any repeated earlier plan.\n"
        f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}{stage}\n"
        f"artifacts: outline={outline_label}; deck={deck_label}; "
        f"patch={patch_label}; html={html_label}; "
        f"generated_images={generated_ready}/{generated_expected}; "
        f"generated_statuses={generated_status_ready}/{generated_expected}; "
        f"qa_ok={qa_ready}/{len(_CONTROLLED_PRESENTATION_REPORTS)}; "
        f"qa_warnings={qa_warnings}.\n"
        "Hard rule: never move backward, never recreate an existing deck, and "
        "never pass --force to the scaffold command after downstream artifacts exist.\n"
        + (f"SCAFFOLD_INPUT={scaffold_input}\n" if scaffold_input is not None else "")
        + (f"IMAGE_INPUT={image_input}\n" if image_input is not None else "")
        + (f"PATCH_INPUT={patch_input}\n" if patch_input is not None else "")
        + (f"REPAIR_INPUT={repair_input}\n" if repair_input is not None else "")
        + (f"RESEARCH_INPUT={research_input}\n" if research_input is not None else "")
        + f"NEXT_ACTION={next_action}"
    )


def completion_gate_gaps(
    gate: CompletionGate,
    succeeded_tools: set[str],
    workspace_dir: str | None,
) -> list[str]:
    """Return human-readable descriptions of unmet gate requirements.

    Empty list means every requirement is satisfied. Pure function: no
    side effects beyond read-only filesystem stats for artifact checks.
    """
    gaps: list[str] = []
    for tool_name in sorted(gate.required_tools):
        if tool_name not in succeeded_tools:
            gaps.append(f"工具 `{tool_name}` 尚未成功调用并返回有效结果")
    base = Path(workspace_dir) if workspace_dir else None
    for artifact in gate.required_artifacts:
        path = Path(artifact)
        if not path.is_absolute() and base is not None:
            path = base / path
        try:
            exists_nonempty = path.is_file() and path.stat().st_size > 0
        except OSError:
            exists_nonempty = False
        if not exists_nonempty:
            gaps.append(f"产物文件 `{artifact}` 不存在或为空")
    changed_artifacts = _changed_artifacts(
        gate.required_changed_artifact_globs,
        gate.baseline_artifact_signatures,
        base,
    )
    if gate.required_changed_artifact_globs and not changed_artifacts:
        patterns = ", ".join(
            f"`{pattern}`" for pattern in gate.required_changed_artifact_globs
        )
        gaps.append(f"尚未产生新的或更新过的交付产物（匹配：{patterns}）")
    report_required_artifacts = [
        path
        for path in changed_artifacts
        if path.suffix.lower() in gate.success_report_artifact_suffixes
    ]
    if (
        gate.required_success_report_globs
        and report_required_artifacts
        and (
            missing_reports := [
                pattern
                for pattern in gate.required_success_report_globs
                if not _has_changed_success_report(
                    (pattern,),
                    gate.baseline_success_report_signatures,
                    base,
                    {path.parent.resolve() for path in report_required_artifacts},
                )
            ]
        )
    ):
        patterns = ", ".join(f"`{pattern}`" for pattern in missing_reports)
        gaps.append(
            "受控演示 QA 尚未完成：需要以下新的或更新过的成功报告"
            f"（匹配：{patterns}，且 JSON `ok` 必须为 true）"
        )
    return gaps


def artifact_signatures_for_globs(
    patterns: tuple[str, ...],
    workspace_dir: str | None,
) -> dict[str, tuple[int, int]]:
    """Snapshot file signatures for artifact glob checks.

    Keys are resolved absolute paths; values are ``(size, mtime_ns)``. Missing
    workspaces simply produce an empty baseline, so later created artifacts can
    still satisfy the gate.
    """
    base = Path(workspace_dir) if workspace_dir else None
    signatures: dict[str, tuple[int, int]] = {}
    for path in _iter_artifact_glob_matches(patterns, base):
        signature = _artifact_signature(path)
        if signature is not None:
            signatures[str(path.resolve())] = signature
    return signatures


def _iter_artifact_glob_matches(
    patterns: tuple[str, ...],
    base: Path | None,
) -> list[Path]:
    matches: list[Path] = []
    for pattern in patterns:
        path_pattern = Path(pattern)
        if path_pattern.is_absolute():
            candidates = [Path(p) for p in glob.glob(pattern, recursive=True)]
        elif base is not None:
            candidates = list(base.glob(pattern))
        else:
            candidates = []
        matches.extend(path for path in candidates if path.is_file())
    return matches


def _artifact_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    if stat.st_size <= 0:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def _has_changed_artifact(
    patterns: tuple[str, ...],
    baseline: dict[str, tuple[int, int]],
    base: Path | None,
) -> bool:
    return bool(_changed_artifacts(patterns, baseline, base))


def _changed_artifacts(
    patterns: tuple[str, ...],
    baseline: dict[str, tuple[int, int]],
    base: Path | None,
) -> list[Path]:
    changed: list[Path] = []
    for path in _iter_artifact_glob_matches(patterns, base):
        signature = _artifact_signature(path)
        if signature is None:
            continue
        try:
            resolved = str(path.resolve())
        except OSError:
            continue
        if baseline.get(resolved) != signature:
            changed.append(path)
    return changed


def _has_changed_success_report(
    patterns: tuple[str, ...],
    baseline: dict[str, tuple[int, int]],
    base: Path | None,
    artifact_roots: set[Path],
) -> bool:
    for report in _changed_artifacts(patterns, baseline, base):
        try:
            report_root = report.parent.parent.resolve()
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if (
            report_root in artifact_roots
            and isinstance(payload, dict)
            and payload.get("ok") is True
        ):
            return True
    return False


def completion_gate_text(gaps: list[str]) -> str:
    """Continuation nudge naming the unmet requirements (same tone as the
    near-limit / no-progress wrap-up nudges)."""
    bullet_lines = "\n".join(f"  - {gap}" for gap in gaps)
    return (
        "⚠️ 本轮任务尚未满足完成条件，请勿在此收尾。仍缺：\n"
        f"{bullet_lines}\n"
        "请补齐以上缺口（完成所需的工具调用、产出缺失的文件），完成后再给出最终答复。"
        "不要空转或仅口头声称已完成——以可验证的实际产出补齐为准。"
    )


def completion_budget_reserve_text(
    gaps: list[str],
    reserve_tool_calls: int,
) -> str:
    """Tell a gated artifact workflow to spend its reserved calls on closure."""
    bullet_lines = "\n".join(f"  - {gap}" for gap in gaps)
    return (
        "⚠️ 已进入交付收尾预算。停止继续浏览主题、布局或校验器源码，也不要重建已有产物。\n"
        f"当前仍缺：\n{bullet_lines}\n"
        f"接下来最多保留 {reserve_tool_calls} 次实质工具调用；只执行完成交付必需的"
        "批量补丁、truth/spec 校验、HTML 渲染、self-check 与 runtime probe。"
        "若确实缺少无法推断的用户事实，调用 `request_user_input` 提出一个聚焦问题并结束本轮；"
        "用户补充后将从当前产物继续。"
    )
