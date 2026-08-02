"""Controlled-presentation workflow policy.

The Agent kernel owns scheduling and tool execution.  This module owns the
presentation-specific stage machine and command/evidence restrictions.
"""

from __future__ import annotations

import json
import logging
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Final

from ..artifacts import artifact_scan_root
from ..evidence import extract_http_urls
from ..tools.base import ToolResult
from ..workflow_policy import WorkflowCheckpointUpdate
from .presentation_checkpoint import build_checkpoint_text
from .presentation_contract import CHECKPOINT_MARKER, WORKFLOW_KIND

DIRECT_RESEARCH_READ_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "browser_open_url",
        "browser_read_page",
        "browser_read_article",
        "browser_navigate",
    }
)
RESEARCH_BUDGET_EXEMPT_TOOLS: Final[frozenset[str]] = (
    DIRECT_RESEARCH_READ_TOOLS | frozenset({"web_search"})
)
RESEARCH_READ_BATCH_SIZE: Final[int] = 2
RESEARCH_ROUND_LIMIT: Final[int] = 3

_log = logging.getLogger(__name__)

_CONTENT_PATCH_BLOCKED_TOOLS: Final[frozenset[str]] = frozenset(
    {"read_file", "execute_code", "bash"}
)
_CONTENT_PATCH_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_PATCH_INPUT_READY: PATCH_INPUT in the latest checkpoint "
    "already contains the exact outline content, slide mapping, prop shapes, and ready "
    "media paths. Do not inspect files again. Write deck.patch.json now with write_file "
    "(and append_file only if the body exceeds the file-tool limit)."
)
_IMAGE_GENERATION_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_IMAGE_INPUT_READY: IMAGE_INPUT already contains the "
    "missing image paths, page intent, and theme palette. Call generate_image now "
    "with an exact listed output_path and watermark=false; do not inspect files or "
    "invent another path."
)
_IMAGE_AUTH_BLOCKED_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_IMAGE_AUTH_BLOCKED: the image service returned HTTP 401 "
    "for this presentation. Do not call generate_image or any other tool again in "
    "this turn. End the turn and report that image generation is blocked until the "
    "service authorization is refreshed."
)
_SCAFFOLD_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_SCAFFOLD_INPUT_READY: SCAFFOLD_INPUT in the latest "
    "checkpoint already contains every registered theme/layout id and every page "
    "intent. Invoke inspect_deck_contract.js once now with --outline outline.json "
    "and --out deck.json; do not reread files, list the registry, or invent ids."
)
_REPAIR_ALLOWED_TOOLS: Final[frozenset[str]] = frozenset(
    {"write_file", "append_file"}
)
_REPAIR_STAGES: Final[frozenset[str]] = frozenset(
    {"outline_repair", "deck_spec_repair"}
)
_REPAIR_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_REPAIR_INPUT_READY: REPAIR_INPUT in the latest "
    "checkpoint already contains the fresh hard deck-spec issues, affected current "
    "props, and outline context. Write the minimal deck.patch.json now; do not reread "
    "stale inputs or run another command first."
)
_OUTLINE_REPAIR_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_OUTLINE_REPAIR_INPUT_READY: REPAIR_INPUT in the "
    "latest checkpoint already contains the complete current outline and fresh "
    "validator issues. Write the corrected outline.json now; do not reread files, "
    "inspect the schema, update todos/plans, or run another command first."
)
_IMAGE_STATUS_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_IMAGE_STATUS_SYNC_REQUIRED: all planned image files "
    "exist. Run sync_image_manifest_status.js once with bash; do not reread/edit "
    "manifest.json or regenerate an existing image."
)
_FINALIZE_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_FINALIZE_REQUIRED: run the single deterministic "
    "finalizer now with bash using the absolute finalize_controlled_deck.js path "
    "from the latest checkpoint, followed by deck.json --out "
    "index.html. It enforces hard spec/media checks, records advisory truth warnings, "
    "compiles HTML, runs self-check, and probes the editor in dependency order. Do "
    "not split that chain into separate validator/render commands or add another "
    "shell command."
)
_APPLY_PATCH_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_APPLY_PATCH_REQUIRED: run the single deterministic "
    "apply_deck_patch.js command from the latest checkpoint with deck.json and "
    "deck.patch.json. Do not substitute another script, compound the command, or "
    "rewrite deck.json directly."
)
_APPLY_PATCH_REPAIR_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_APPLY_PATCH_REPAIR_REQUIRED: the latest deterministic "
    "apply_deck_patch.js call returned an actionable error. You may only read, edit, "
    "or rewrite deck.patch.json with the minimal named-field repair, "
    "replace a required unavailable fact with an explicit placeholder, omit an "
    "unsupported optional claim, or rerun the exact apply command. Do not ask for "
    "missing facts, read or rewrite deck.json, or run discovery commands."
)
_APPLY_PATCH_FIELD_MISMATCH = (
    "CONTROLLED_PRESENTATION_APPLY_PATCH_FIELD_MISMATCH: the proposed deck.patch.json "
    "repair does not change any field named by the latest deterministic error. "
    "Change one of these exact fields and leave unrelated slide content unchanged: {paths}."
)
_REPAIR_STALLED_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_REPAIR_STALLED: two consecutive repair tool attempts "
    "failed to make progress. Do not repeat the call or bypass the stage guard with "
    "a compound shell command, and do not ask for missing facts. End this turn and "
    "report the unresolved internal validation conflict."
)
_PLAN_SCOPE_ERROR = (
    "CONTROLLED_PRESENTATION_PLAN_SCOPE_INCOMPLETE: the user requested a finished "
    "presentation, so the execution plan cannot stop at outline/content planning. "
    "Publish a corrected plan that covers outline.json, deck.json scaffolding, "
    "content/media authoring, deterministic index.html finalization, and QA. Only "
    "an explicit user request for outline-only output may omit those delivery stages."
)
_PLAN_OUTLINE_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"(?:本轮|当前|这次)?[^。；;\n]{0,16}(?:仅|只)"
    r"[^。；;\n]{0,32}(?:outline|大纲|内容方案)"
    r"|(?:不进入|不生成|不制作|不渲染|不包含)"
    r"[^。；;\n]{0,32}(?:html|pptx?|页面|幻灯片|主题|版式|布局|脚手架|deck)"
    r"|\b(?:outline[- ]only|only\s+(?:produce|create|deliver)?\s*outline|"
    r"do\s+not\s+(?:generate|create|render|deliver)\s+"
    r"(?:slides?|pages?|html|deck))\b"
    r")",
    re.IGNORECASE,
)
_PLAN_DELIVERY_STEP_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:deck\.json|index\.html|finalize_controlled_deck|"
    r"(?:生成|制作|编译|渲染|交付|导出)[^。；;\n]{0,32}"
    r"(?:html|pptx?|页面|幻灯片|deck)|"
    r"\b(?:scaffold|render|compile|finalize|deliver|export)\b)",
    re.IGNORECASE,
)
_RESEARCH_HANDOFF_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_RESEARCH_HANDOFF_READY: research QA is complete. "
    "Do not search/browse, create or update todos/plans, reread outline.md or the "
    "research QA report, or inspect/list the filesystem. Read only a Markdown "
    "handoff file explicitly named in RESEARCH_INPUT when its content is missing "
    "from context; otherwise write outline.json now."
)
_RESEARCH_SEARCH_COMPLETE_TOOL_ERROR = (
    "CONTROLLED_PRESENTATION_RESEARCH_SEARCH_COMPLETE: bounded research searches "
    "already returned usable evidence. Do not call web_search or a browser read tool "
    "again. Complete the cross-verification, insight, evidence ledger, and validation "
    "report from the evidence already in context."
)

_PPTX_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "document-skills"
    / "pptx"
    / "scripts"
)
_FINALIZER_SCRIPT = _PPTX_SCRIPTS_DIR / "finalize_controlled_deck.js"
_INSPECT_SCRIPT = _PPTX_SCRIPTS_DIR / "inspect_deck_contract.js"
_APPLY_PATCH_SCRIPT = _PPTX_SCRIPTS_DIR / "apply_deck_patch.js"
_VALIDATE_OUTLINE_SCRIPT = _PPTX_SCRIPTS_DIR / "validate_outline.js"
_JSON_MISSING = object()


def _plan_scope_error(
    stage: str | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    if (
        stage in {None, "complete"}
        or tool_name != "plan_write"
        or str(arguments.get("action") or "").lower() != "set"
    ):
        return None
    restrictive_text = json.dumps(
        {
            "objective": arguments.get("objective"),
            "scope": arguments.get("scope"),
            "risks": arguments.get("risks"),
            "assumptions": arguments.get("assumptions"),
        },
        ensure_ascii=False,
        default=str,
    )
    if not _PLAN_OUTLINE_ONLY_RE.search(restrictive_text):
        return None
    delivery_text = json.dumps(
        {
            "steps": arguments.get("steps"),
            "verification": arguments.get("verification"),
        },
        ensure_ascii=False,
        default=str,
    )
    if _PLAN_DELIVERY_STEP_RE.search(delivery_text):
        return None
    return _PLAN_SCOPE_ERROR


def _image_status_error(
    stage: str | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    if stage != "image_status_sync":
        return None
    command = arguments.get("command")
    if (
        tool_name == "bash"
        and isinstance(command, str)
        and "sync_image_manifest_status.js" in command
        and "assets/generated/manifest.json" in command
    ):
        return None
    return _IMAGE_STATUS_TOOL_ERROR


def _finalize_error(
    stage: str | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    if stage != "finalize":
        return None
    command = arguments.get("command")
    if tool_name != "bash" or not isinstance(command, str):
        return _FINALIZE_TOOL_ERROR
    try:
        tokens = shlex.split(command)
    except ValueError:
        return _FINALIZE_TOOL_ERROR
    script_indexes = [
        index
        for index, token in enumerate(tokens)
        if Path(token).name == "finalize_controlled_deck.js"
    ]
    if len(script_indexes) != 1:
        return _FINALIZE_TOOL_ERROR
    script_index = script_indexes[0]
    if script_index < 1:
        return _FINALIZE_TOOL_ERROR
    node_token = tokens[script_index - 1]
    if not (
        Path(node_token).name in {"node", "node.exe"}
        or "BOX_AGENT_NODE" in node_token
    ):
        return _FINALIZE_TOOL_ERROR
    supplied_script = Path(tokens[script_index])
    if (
        not supplied_script.is_absolute()
        or supplied_script.resolve() != _FINALIZER_SCRIPT
    ):
        return _FINALIZE_TOOL_ERROR
    command_prefix = tokens[: script_index - 1]
    if command_prefix and not (
        len(command_prefix) == 3
        and command_prefix[0] == "cd"
        and command_prefix[1]
        and command_prefix[2] == "&&"
    ):
        return _FINALIZE_TOOL_ERROR
    finalizer_args = tokens[script_index + 1 :]
    if (
        len(finalizer_args) == 3
        and Path(finalizer_args[0]).name == "deck.json"
        and finalizer_args[1] == "--out"
        and Path(finalizer_args[2]).name == "index.html"
    ):
        return None
    return _FINALIZE_TOOL_ERROR


def _finalizer_failure_signature(
    tool_name: str,
    arguments: dict[str, Any],
    result: ToolResult,
) -> str | None:
    if result.success or _finalize_error("finalize", tool_name, arguments):
        return None
    payload = "\n".join(
        part for part in (result.error, result.content) if isinstance(part, str) and part
    )
    if not payload.strip():
        return "empty-finalizer-failure"
    marker = payload.find("FINALIZE_STOP")
    semantic = payload[marker:] if marker >= 0 else payload
    return re.sub(r"\s+", " ", semantic).strip()[:4000]


def _is_outline_validation_call(
    tool_name: str,
    arguments: dict[str, Any],
) -> bool:
    if tool_name != "bash":
        return False
    command = arguments.get("command")
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    script_tokens = [
        token
        for token in tokens
        if Path(token).name == "validate_outline.js"
    ]
    if len(script_tokens) != 1:
        return False
    supplied_script = Path(script_tokens[0])
    return (
        supplied_script.is_absolute()
        and supplied_script.resolve() == _VALIDATE_OUTLINE_SCRIPT
    )


def _outline_validation_failure_signature(
    tool_name: str,
    arguments: dict[str, Any],
    result: ToolResult,
    workspace_dir: str | None,
) -> str | None:
    if result.success or not _is_outline_validation_call(tool_name, arguments):
        return None

    report_candidates: list[Path] = []
    command = arguments.get("command")
    try:
        tokens = shlex.split(command) if isinstance(command, str) else []
    except ValueError:
        tokens = []
    if "--report" in tokens:
        report_index = tokens.index("--report") + 1
        if report_index < len(tokens):
            requested_report = Path(tokens[report_index])
            if requested_report.is_absolute():
                report_candidates.append(requested_report)
            elif workspace_dir:
                root = Path(workspace_dir)
                report_candidates.extend(
                    (root / requested_report, root / "output" / requested_report)
                )
    if workspace_dir:
        report_candidates.extend(
            (Path(workspace_dir) / "output").rglob("outline_check.json")
        )
    existing_reports = [path for path in report_candidates if path.is_file()]
    if existing_reports:
        report_path = max(existing_reports, key=lambda path: path.stat().st_mtime_ns)
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = None
        if isinstance(report, dict) and report.get("ok") is False:
            semantic = {
                "issues": report.get("issues") or [],
                "warnings": report.get("warnings") or [],
            }
            return json.dumps(
                semantic,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )[:4000]

    payload = "\n".join(
        part for part in (result.error, result.content) if isinstance(part, str) and part
    )
    return re.sub(r"\s+", " ", payload).strip()[:4000] or "empty-outline-failure"


def _failure_field_paths(result: ToolResult) -> tuple[str, ...]:
    payload = "\n".join(
        part for part in (result.error, result.content) if isinstance(part, str) and part
    )
    return tuple(
        dict.fromkeys(
            re.findall(
                r"(?m)^((?:slides)(?:\.[A-Za-z0-9_-]+){2,}):",
                payload,
            )
        )
    )


def _patch_file(
    workspace_dir: str | None,
    requested_path: str,
) -> Path | None:
    requested = Path(requested_path)
    candidates: list[Path] = []
    if requested.is_absolute():
        candidates.append(requested)
    elif workspace_dir:
        root = Path(workspace_dir)
        candidates.extend((root / requested, root / "output" / requested))
        if requested.name == "deck.patch.json":
            candidates.extend((root / "output").rglob("deck.patch.json"))
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime_ns)


def _json_path_value(document: Any, field_path: str) -> Any:
    parts = field_path.split(".")
    if (
        parts[:1] == ["slides"]
        and isinstance(document, dict)
        and not isinstance(document.get("slides"), dict)
        and len(parts) > 1
        and isinstance(document.get(parts[1]), dict)
    ):
        parts = parts[1:]
    current = document
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, dict) and part.isdigit():
            slide_keys = sorted(
                (
                    key
                    for key in current
                    if isinstance(key, str) and re.fullmatch(r"slide-\d+", key)
                ),
                key=lambda key: int(key.rsplit("-", 1)[-1]),
            )
            index = int(part)
            if index >= len(slide_keys):
                return _JSON_MISSING
            current = current[slide_keys[index]]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _JSON_MISSING
    return current


def _patch_repair_changes_named_field(
    tool_name: str,
    arguments: dict[str, Any],
    workspace_dir: str | None,
    repair_paths: tuple[str, ...],
) -> bool:
    if not repair_paths:
        return True
    patch_arg = arguments.get("path")
    if not isinstance(patch_arg, str):
        return False
    patch_file = _patch_file(workspace_dir, patch_arg)
    try:
        before_text = patch_file.read_text(encoding="utf-8") if patch_file else "{}"
        before = json.loads(before_text)
        if tool_name == "write_file":
            after_text = arguments.get("content")
        elif tool_name == "edit_file":
            old_str = arguments.get("old_str")
            new_str = arguments.get("new_str")
            if (
                not isinstance(old_str, str)
                or not isinstance(new_str, str)
                or old_str not in before_text
            ):
                return False
            after_text = before_text.replace(old_str, new_str, 1)
        else:
            return False
        if not isinstance(after_text, str):
            return False
        after = json.loads(after_text)
    except (OSError, json.JSONDecodeError):
        return False
    return any(
        _json_path_value(before, path) != _json_path_value(after, path)
        for path in repair_paths
    )


def _apply_patch_error(
    stage: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    repair_allowed: bool = False,
    repair_paths: tuple[str, ...] = (),
    workspace_dir: str | None = None,
) -> str | None:
    if stage != "apply_patch":
        return None
    if repair_allowed:
        patch_path = arguments.get("path")
        safe_patch_path = (
            isinstance(patch_path, str)
            and Path(patch_path).name == "deck.patch.json"
            and ".." not in Path(patch_path).parts
        )
        if tool_name == "read_file" and safe_patch_path:
            return None
        if (
            tool_name == "write_file"
            and safe_patch_path
            and isinstance(arguments.get("content"), str)
        ):
            return (
                None
                if _patch_repair_changes_named_field(
                    tool_name,
                    arguments,
                    workspace_dir,
                    repair_paths,
                )
                else _APPLY_PATCH_FIELD_MISMATCH.format(
                    paths=", ".join(repair_paths)
                )
            )
        if (
            tool_name == "edit_file"
            and safe_patch_path
            and isinstance(arguments.get("old_str"), str)
            and isinstance(arguments.get("new_str"), str)
        ):
            return (
                None
                if _patch_repair_changes_named_field(
                    tool_name,
                    arguments,
                    workspace_dir,
                    repair_paths,
                )
                else _APPLY_PATCH_FIELD_MISMATCH.format(
                    paths=", ".join(repair_paths)
                )
            )
    command = arguments.get("command")
    if tool_name != "bash" or not isinstance(command, str):
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    try:
        tokens = shlex.split(command)
    except ValueError:
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    script_indexes = [
        index
        for index, token in enumerate(tokens)
        if Path(token).name == "apply_deck_patch.js"
    ]
    if len(script_indexes) != 1:
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    script_index = script_indexes[0]
    if script_index < 1:
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    node_token = tokens[script_index - 1]
    if not (
        Path(node_token).name in {"node", "node.exe"}
        or "BOX_AGENT_NODE" in node_token
    ):
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    supplied_script = Path(tokens[script_index])
    if (
        not supplied_script.is_absolute()
        or supplied_script.resolve() != _APPLY_PATCH_SCRIPT
    ):
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    command_prefix = tokens[: script_index - 1]
    if command_prefix and not (
        len(command_prefix) == 3
        and command_prefix[0] == "cd"
        and command_prefix[1]
        and command_prefix[2] == "&&"
    ):
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    if tokens[script_index + 1 :] != ["deck.json", "deck.patch.json"]:
        return _APPLY_PATCH_REPAIR_TOOL_ERROR if repair_allowed else _APPLY_PATCH_TOOL_ERROR
    return None


def _apply_patch_failure_signature(
    tool_name: str,
    arguments: dict[str, Any],
    result: ToolResult,
) -> str | None:
    if result.success or _apply_patch_error("apply_patch", tool_name, arguments):
        return None
    payload = "\n".join(
        part for part in (result.error, result.content) if isinstance(part, str) and part
    )
    if not payload.strip():
        return "empty-apply-patch-failure"
    marker = payload.find("Error:")
    semantic = payload[marker:] if marker >= 0 else payload
    return re.sub(r"\s+", " ", semantic).strip()[:4000]


def _repair_stalled_checkpoint() -> str:
    return (
        "Internal controlled-presentation checkpoint; the same deterministic "
        "controlled-deck step failed twice with the same error, so filesystem writes are now "
        "stopped to prevent an unbounded repair loop.\n"
        f"{CHECKPOINT_MARKER}repair_stalled\n"
        "NEXT_ACTION=Do not call another write/apply/finalize or validation tool. "
        "Do not ask for missing facts; they must already have been represented by "
        "explicit placeholders or omitted when optional. End the turn and state that "
        "delivery is incomplete because of a repeated internal validation conflict."
    )


def _image_auth_blocked_checkpoint() -> str:
    return (
        "Internal controlled-presentation checkpoint; the image service returned "
        "HTTP 401, which is a non-retryable authorization failure for this turn. "
        "Further image requests are stopped to prevent an unbounded retry loop.\n"
        f"{CHECKPOINT_MARKER}image_auth_blocked\n"
        "NEXT_ACTION=Do not call generate_image or any other tool again. End the "
        "turn and state that delivery is incomplete because image generation "
        "authorization must be refreshed before retrying."
    )


def _checkpoint_json(
    checkpoint_text: str,
    label: str,
) -> dict[str, Any] | None:
    prefix = f"{label}="
    for line in checkpoint_text.splitlines():
        if not line.startswith(prefix):
            continue
        try:
            value = json.loads(line[len(prefix) :])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    return None


def _research_handoff_urls(
    checkpoint_text: str,
    workspace_dir: str | None,
    artifact_root_dir: str | Path | None,
) -> set[str]:
    research_input = _checkpoint_json(checkpoint_text, "RESEARCH_INPUT")
    if not research_input or research_input.get("ready") is not True:
        return set()
    root = artifact_scan_root(workspace_dir, artifact_root_dir)
    if root is None:
        return set()
    root = root.resolve()
    urls: set[str] = set()
    files = research_input.get("files")
    if not isinstance(files, list):
        return urls
    for relative_path in files:
        if not isinstance(relative_path, str) or not relative_path.endswith(".md"):
            continue
        candidate = (root / relative_path).resolve()
        if not candidate.is_relative_to(root):
            continue
        try:
            if not candidate.is_file() or candidate.stat().st_size > 4 * 1024 * 1024:
                continue
            urls.update(extract_http_urls(candidate.read_text(encoding="utf-8")))
        except OSError:
            continue
    return urls


def _research_handoff_error(
    stage: str | None,
    research_mode: str | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> str | None:
    if stage != "outline" or research_mode != "deep":
        return None
    if tool_name == "request_user_input":
        return None
    if tool_name == "write_file":
        path = arguments.get("path")
        if isinstance(path, str) and Path(path).name == "outline.json":
            return None
    if tool_name == "read_file":
        path = arguments.get("path")
        if isinstance(path, str):
            candidate = Path(path)
            if (
                candidate.suffix.casefold() == ".md"
                and candidate.name.casefold() != "outline.md"
                and "research" in {part.casefold() for part in candidate.parts}
            ):
                return None
    return _RESEARCH_HANDOFF_TOOL_ERROR


def _scaffold_error(
    tool_name: str,
    arguments: dict[str, Any],
    scaffold_input: dict[str, Any] | None,
) -> str | None:
    if scaffold_input is None:
        return None
    command = arguments.get("command")
    if tool_name != "bash" or not isinstance(command, str):
        return _SCAFFOLD_TOOL_ERROR
    try:
        tokens = shlex.split(command)
    except ValueError:
        return _SCAFFOLD_TOOL_ERROR
    script_indexes = [
        index
        for index, token in enumerate(tokens)
        if Path(token).name == "inspect_deck_contract.js"
    ]
    script_index = script_indexes[0] if script_indexes else None
    if script_index is None or "--outline" not in tokens or "--out" not in tokens:
        return _SCAFFOLD_TOOL_ERROR

    registered_layouts = {
        item
        for item in scaffold_input.get("registered_layout_ids", [])
        if isinstance(item, str)
    }
    layout_ids: list[str] = []
    for token in tokens[script_index + 1 :]:
        if token.startswith("--"):
            break
        layout_ids.append(token)
    invalid_layouts = [item for item in layout_ids if item not in registered_layouts]

    registered_themes = {
        item
        for item in scaffold_input.get("registered_theme_ids", [])
        if isinstance(item, str)
    }
    invalid_theme: str | None = None
    if "--theme" in tokens:
        theme_index = tokens.index("--theme") + 1
        if (
            theme_index >= len(tokens)
            or (
                tokens[theme_index].lower() != "auto"
                and tokens[theme_index] not in registered_themes
            )
        ):
            invalid_theme = tokens[theme_index] if theme_index < len(tokens) else "<missing>"
    if invalid_layouts or invalid_theme is not None:
        details = []
        if invalid_theme is not None:
            details.append(f"invalid theme id {invalid_theme!r}")
        if invalid_layouts:
            details.append(f"invalid layout ids {invalid_layouts!r}")
        return (
            "CONTROLLED_PRESENTATION_INVALID_REGISTRY_ID: "
            + "; ".join(details)
            + ". Choose exact ids from SCAFFOLD_INPUT and invoke "
            "inspect_deck_contract.js once; the invalid command was not executed."
        )

    if len(script_indexes) != 1 or script_index < 1:
        return _SCAFFOLD_TOOL_ERROR
    node_token = tokens[script_index - 1]
    if not (
        Path(node_token).name in {"node", "node.exe"}
        or "BOX_AGENT_NODE" in node_token
    ):
        return _SCAFFOLD_TOOL_ERROR
    supplied_script = Path(tokens[script_index])
    if not supplied_script.is_absolute() or supplied_script.resolve() != _INSPECT_SCRIPT:
        return _SCAFFOLD_TOOL_ERROR
    command_prefix = tokens[: script_index - 1]
    if command_prefix and not (
        len(command_prefix) == 3
        and command_prefix[0] == "cd"
        and command_prefix[1]
        and command_prefix[2] == "&&"
    ):
        return _SCAFFOLD_TOOL_ERROR
    inspector_args = tokens[script_index + 1 :]
    if any(
        token in {"&&", "||", ";", "|", "&", ">", ">>", "<", "<<"}
        for token in inspector_args
    ):
        return _SCAFFOLD_TOOL_ERROR
    if tokens.count("--outline") != 1 or tokens.count("--out") != 1:
        return _SCAFFOLD_TOOL_ERROR
    outline_index = tokens.index("--outline") + 1
    out_index = tokens.index("--out") + 1
    if (
        outline_index >= len(tokens)
        or out_index >= len(tokens)
        or Path(tokens[outline_index]).name != "outline.json"
        or Path(tokens[out_index]).name != "deck.json"
    ):
        return _SCAFFOLD_TOOL_ERROR
    return None


def _scaffold_failure_signature(
    tool_name: str,
    arguments: dict[str, Any],
    result: ToolResult,
    scaffold_input: dict[str, Any] | None,
) -> str | None:
    if (
        result.success
        or scaffold_input is None
        or _scaffold_error(tool_name, arguments, scaffold_input)
    ):
        return None
    payload = "\n".join(
        part for part in (result.error, result.content) if isinstance(part, str) and part
    )
    if not payload.strip():
        return "empty-scaffold-failure"
    marker = payload.find("Error:")
    semantic = payload[marker:] if marker >= 0 else payload
    return re.sub(r"\s+", " ", semantic).strip()[:4000]


def _image_generation_error(
    stage: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    image_input: dict[str, Any] | None,
) -> str | None:
    if stage != "images" or image_input is None:
        return None
    entries = image_input.get("entries")
    expected_paths = {
        entry.get("output_path")
        for entry in entries or []
        if isinstance(entry, dict) and isinstance(entry.get("output_path"), str)
    }
    if (
        tool_name == "generate_image"
        and arguments.get("output_path") in expected_paths
        and arguments.get("watermark") is False
    ):
        return None
    return _IMAGE_GENERATION_TOOL_ERROR


def _stage(checkpoint_text: str) -> str | None:
    marker_index = checkpoint_text.find(CHECKPOINT_MARKER)
    if marker_index < 0:
        return None
    stage_text = checkpoint_text[marker_index + len(CHECKPOINT_MARKER) :]
    stage = stage_text.splitlines()[0].strip()
    return stage or None


def _research_result_is_empty(result: ToolResult) -> bool:
    """Return whether a successful research tool call yielded no usable payload."""
    if not result.success:
        return False
    content = (result.model_context or result.content or "").strip()
    if not content:
        return True
    return content.casefold() in {
        "[]",
        "{}",
        "null",
        "no results",
        "no search results",
        "no results found",
    }


def _image_result_is_unauthorized(result: ToolResult) -> bool:
    """Return whether image generation failed with a deterministic HTTP 401."""
    if result.success:
        return False
    raw_output = result.raw_output
    if isinstance(raw_output, dict) and raw_output.get("status_code") == 401:
        return True
    payload = "\n".join(
        part
        for part in (result.error, result.content, result.model_context)
        if isinstance(part, str) and part
    )
    return re.search(r"(?<!\d)401(?!\d)", payload) is not None


@dataclass(slots=True)
class ControlledPresentationPolicy:
    """Stateful policy for one controlled-presentation agent run."""

    workspace_dir: str | None
    artifact_root_dir: str | Path | None
    research_mode: str | None = None
    stage: str | None = None
    scaffold_input: dict[str, Any] | None = None
    image_input: dict[str, Any] | None = None
    has_patch_input: bool = False
    has_scaffold_input: bool = False
    has_image_input: bool = False
    has_repair_input: bool = False
    repair_stalled: bool = False
    image_auth_blocked: bool = False
    research_search_exhausted: bool = False
    apply_patch_repair_allowed: bool = False
    apply_patch_repair_paths: tuple[str, ...] = ()
    _last_checkpoint_text: str | None = None
    _step_failure_counts: dict[str, int] = field(default_factory=dict)
    _repair_failure_stage: str | None = None
    _repair_failure_streak: int = 0
    _research_tool_attempts: int = 0
    _research_successful_attempts: int = 0
    _research_failed_attempts: int = 0
    _research_empty_attempts: int = 0
    _research_calls_since_checkpoint: int = 0
    _research_rounds_without_handoff: int = 0

    kind: ClassVar[str] = WORKFLOW_KIND
    checkpoint_injection_id: ClassVar[str] = CHECKPOINT_MARKER
    evidence_read_batch_size: ClassVar[int] = RESEARCH_READ_BATCH_SIZE

    def build_checkpoint(self) -> str | None:
        """Derive the current presentation stage from persisted artifacts."""
        if self.image_auth_blocked:
            return _image_auth_blocked_checkpoint()
        if self._research_calls_since_checkpoint:
            self._research_rounds_without_handoff += 1
            self._research_calls_since_checkpoint = 0
        round_limit_reached = (
            self._research_rounds_without_handoff >= RESEARCH_ROUND_LIMIT
        )
        unavailable = self._research_failed_attempts + self._research_empty_attempts
        fallback_allowed = (
            round_limit_reached
            and self._research_tool_attempts > 0
            and unavailable == self._research_tool_attempts
        )
        self.research_search_exhausted = round_limit_reached and not fallback_allowed
        attempt_summary = {
            "rounds": self._research_rounds_without_handoff,
            "calls": self._research_tool_attempts,
            "successful": self._research_successful_attempts,
            "failed": self._research_failed_attempts,
            "empty": self._research_empty_attempts,
        }
        fallback_reason = None
        if fallback_allowed:
            fallback_reason = "research_sources_unavailable"
        checkpoint_text = build_checkpoint_text(
            self.workspace_dir,
            self.research_mode,
            research_fallback_allowed=fallback_allowed,
            research_fallback_reason=fallback_reason,
            research_attempt_summary=attempt_summary,
            research_search_exhausted=self.research_search_exhausted,
        )
        research_input = (
            _checkpoint_json(checkpoint_text, "RESEARCH_INPUT")
            if checkpoint_text is not None
            else None
        )
        if research_input and research_input.get("fallback") is True:
            self._persist_research_fallback_status(research_input)
        return checkpoint_text

    def _persist_research_fallback_status(
        self,
        research_input: dict[str, Any],
    ) -> None:
        """Persist why PPT generation continued without a validated report."""
        root = artifact_scan_root(self.workspace_dir, self.artifact_root_dir)
        if root is None:
            return
        status_path = root / "research" / "qa" / "research_status.json"
        payload = {
            "schema_version": 1,
            "workflow": WORKFLOW_KIND,
            "research_mode": self.research_mode,
            "status": "fallback",
            "report_available": False,
            "generation_continues": True,
            "continued_to": "outline",
            "reason": research_input.get("fallback_reason"),
            "message": research_input.get("fallback_message"),
            "attempt_summary": research_input.get("attempt_summary", {}),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        try:
            if status_path.is_file():
                if status_path.read_text(encoding="utf-8") == serialized:
                    return
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(serialized, encoding="utf-8")
        except OSError as exc:
            _log.warning(
                "controlled_presentation/research_status_write_failed "
                "path=%s error=%s",
                status_path,
                exc,
            )

    def update_checkpoint(
        self,
        checkpoint_text: str,
    ) -> WorkflowCheckpointUpdate:
        """Parse a fresh filesystem checkpoint and update policy state."""
        if self.repair_stalled:
            checkpoint_text = _repair_stalled_checkpoint()
        next_stage = _stage(checkpoint_text)
        if next_stage != self._repair_failure_stage:
            self._repair_failure_stage = (
                next_stage if next_stage in _REPAIR_STAGES else None
            )
            self._repair_failure_streak = 0
        self.stage = next_stage
        self.has_patch_input = "\nPATCH_INPUT=" in checkpoint_text
        self.has_scaffold_input = "\nSCAFFOLD_INPUT=" in checkpoint_text
        self.scaffold_input = _checkpoint_json(checkpoint_text, "SCAFFOLD_INPUT")
        self.has_image_input = "\nIMAGE_INPUT=" in checkpoint_text
        self.image_input = _checkpoint_json(checkpoint_text, "IMAGE_INPUT")
        self.has_repair_input = "\nREPAIR_INPUT=" in checkpoint_text

        changed = checkpoint_text != self._last_checkpoint_text
        recovered_urls = (
            _research_handoff_urls(
                checkpoint_text,
                self.workspace_dir,
                self.artifact_root_dir,
            )
            if changed
            else set()
        )
        if changed:
            self._last_checkpoint_text = checkpoint_text
        return WorkflowCheckpointUpdate(
            text=checkpoint_text,
            changed=changed,
            recovered_evidence_urls=frozenset(recovered_urls),
        )

    def plan_scope_error(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str | None:
        """Validate a structured plan before host approval handling."""
        return _plan_scope_error(self.stage, tool_name, arguments)

    def tool_call_error(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        verified_evidence_urls: set[str],
        parallel: bool = False,
    ) -> str | None:
        """Return a blocking error for a workflow-invalid tool call."""
        handoff_error = _research_handoff_error(
            self.stage,
            self.research_mode,
            tool_name,
            arguments,
        )
        if parallel:
            if self.stage == "image_auth_blocked":
                return _IMAGE_AUTH_BLOCKED_TOOL_ERROR
            if (
                self.stage == "research"
                and self.research_search_exhausted
                and tool_name in RESEARCH_BUDGET_EXEMPT_TOOLS
            ):
                return _RESEARCH_SEARCH_COMPLETE_TOOL_ERROR
            return handoff_error
        if self.stage == "repair_stalled":
            return _REPAIR_STALLED_TOOL_ERROR
        if self.stage == "image_auth_blocked":
            return _IMAGE_AUTH_BLOCKED_TOOL_ERROR
        if handoff_error is not None:
            return handoff_error
        if (
            self.stage == "research"
            and self.research_search_exhausted
            and tool_name in RESEARCH_BUDGET_EXEMPT_TOOLS
        ):
            return _RESEARCH_SEARCH_COMPLETE_TOOL_ERROR
        if (
            self.stage == "content_patch"
            and self.has_patch_input
            and tool_name in _CONTENT_PATCH_BLOCKED_TOOLS
        ):
            return _CONTENT_PATCH_TOOL_ERROR
        if self.stage == "scaffold" and self.has_scaffold_input:
            scaffold_error = _scaffold_error(
                tool_name,
                arguments,
                self.scaffold_input,
            )
            if scaffold_error is not None:
                return scaffold_error
        if self.stage == "images" and self.has_image_input:
            image_error = _image_generation_error(
                self.stage,
                tool_name,
                arguments,
                self.image_input,
            )
            if image_error is not None:
                return image_error
        if (
            self.stage == "outline_repair"
            and self.has_repair_input
            and tool_name != "write_file"
        ):
            return _OUTLINE_REPAIR_TOOL_ERROR
        if (
            self.stage == "deck_spec_repair"
            and self.has_repair_input
            and tool_name not in _REPAIR_ALLOWED_TOOLS
        ):
            return _REPAIR_TOOL_ERROR
        image_status_error = _image_status_error(self.stage, tool_name, arguments)
        if image_status_error is not None:
            return image_status_error
        apply_patch_error = _apply_patch_error(
            self.stage,
            tool_name,
            arguments,
            repair_allowed=self.apply_patch_repair_allowed,
            repair_paths=self.apply_patch_repair_paths,
            workspace_dir=self.workspace_dir,
        )
        if apply_patch_error is not None:
            return apply_patch_error
        return _finalize_error(self.stage, tool_name, arguments)

    def record_tool_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> None:
        """Update deterministic-repair state after one tool result."""
        if (
            self.stage == "images"
            and tool_name == "generate_image"
            and _image_result_is_unauthorized(result)
        ):
            self.image_auth_blocked = True
            _log.warning(
                "controlled_presentation/image_auth_blocked status=401 "
                "further_image_calls_stopped=true"
            )

        if self.stage == "research" and tool_name in RESEARCH_BUDGET_EXEMPT_TOOLS:
            self._research_tool_attempts += 1
            self._research_calls_since_checkpoint += 1
            if not result.success:
                self._research_failed_attempts += 1
            elif _research_result_is_empty(result):
                self._research_empty_attempts += 1
            else:
                self._research_successful_attempts += 1

        if self.stage in _REPAIR_STAGES:
            if result.success:
                self._repair_failure_streak = 0
            else:
                self._repair_failure_stage = self.stage
                self._repair_failure_streak += 1
                if self._repair_failure_streak >= 2:
                    self.repair_stalled = True
                    _log.warning(
                        "controlled_presentation/repair_stalled "
                        "stage=%s consecutive_failed_tools=%d",
                        self.stage,
                        self._repair_failure_streak,
                    )
            return

        if self.stage == "apply_patch" and result.success:
            patch_path = arguments.get("path")
            wrote_patch = (
                tool_name in {"write_file", "edit_file"}
                and isinstance(patch_path, str)
                and Path(patch_path).name == "deck.patch.json"
                and ".." not in Path(patch_path).parts
            )
            applied_patch = (
                tool_name == "bash"
                and _apply_patch_error(self.stage, tool_name, arguments) is None
            )
            if wrote_patch or applied_patch:
                for key in tuple(self._step_failure_counts):
                    if key.startswith("apply_patch:"):
                        self._step_failure_counts.pop(key, None)
            if applied_patch:
                self.apply_patch_repair_allowed = False
                self.apply_patch_repair_paths = ()

        if self.stage == "outline_qa":
            if result.success and _is_outline_validation_call(tool_name, arguments):
                for key in tuple(self._step_failure_counts):
                    if key.startswith("outline_qa:"):
                        self._step_failure_counts.pop(key, None)
                signature = None
            else:
                signature = _outline_validation_failure_signature(
                    tool_name,
                    arguments,
                    result,
                    self.workspace_dir,
                )
        elif self.stage == "finalize":
            signature = _finalizer_failure_signature(
                tool_name,
                arguments,
                result,
            )
        elif self.stage == "apply_patch":
            signature = _apply_patch_failure_signature(
                tool_name,
                arguments,
                result,
            )
            if signature is not None:
                self.apply_patch_repair_allowed = True
                named_paths = _failure_field_paths(result)
                if named_paths:
                    self.apply_patch_repair_paths = named_paths
        elif self.stage == "scaffold":
            signature = _scaffold_failure_signature(
                tool_name,
                arguments,
                result,
                self.scaffold_input,
            )
        else:
            signature = None

        if signature is None:
            return
        scoped_signature = f"{self.stage}:{signature}"
        repeat_count = self._step_failure_counts.get(scoped_signature, 0) + 1
        self._step_failure_counts[scoped_signature] = repeat_count
        if repeat_count >= 2:
            self.repair_stalled = True
            _log.warning(
                "controlled_presentation/repair_stalled stage=%s repeated_failure=%d",
                self.stage,
                repeat_count,
            )

    def exempts_tool_budget(self, tool_name: str) -> bool:
        """Return whether a research-stage call is exempt from delivery budget."""
        return self.stage == "research" and tool_name in RESEARCH_BUDGET_EXEMPT_TOOLS

    def uses_evidence_read_budget(self, tool_name: str) -> bool:
        """Return whether this call uses the bounded direct-read batch."""
        return self.stage == "research" and tool_name in DIRECT_RESEARCH_READ_TOOLS

    @staticmethod
    def is_direct_evidence_read_tool(tool_name: str) -> bool:
        """Return whether a successful result can establish URL provenance."""
        return tool_name in DIRECT_RESEARCH_READ_TOOLS

    def allows_completion_continuation(self) -> bool:
        return self.stage not in {"complete", "repair_stalled", "image_auth_blocked"}

    def suppresses_generic_final_summary(self) -> bool:
        return self.stage not in {
            None,
            "complete",
            "repair_stalled",
            "image_auth_blocked",
        }
