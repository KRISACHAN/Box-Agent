"""File operation tools."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

from ..events import ProgressEvent
from ..model_history import (
    is_model_history_placeholder,
    is_model_instruction_source_path,
)
from .base import EventEmittingTool, Tool, ToolResult
from .pptx_safety import detect_pptx_self_check_bypass
from .safety import backup_file, validate_path_in_workspace

if TYPE_CHECKING:
    from .permissions import PermissionEngine


_MODEL_CONTEXT_EXTS = {".html", ".htm", ".json", ".md", ".txt", ".log", ".xml"}
_MODEL_CONTEXT_PATH_PARTS = {"qa", "rendered", "slides", "vision_inputs"}
_MODEL_CONTEXT_SIZE_THRESHOLD = 8_000
MAX_FILE_TOOL_CONTENT_CHARS = 8_000
MAX_FILE_TOOL_CONTENT_CHARS_DISPLAY = f"{MAX_FILE_TOOL_CONTENT_CHARS:,}"
DEFAULT_READ_LIMIT = 500
MAX_READ_LINES = 2_000
MAX_READ_CHARS = 100_000
DEFAULT_SEARCH_LIMIT = 50
MAX_SEARCH_RESULTS = 200
DEFAULT_SEARCH_TIMEOUT_SECONDS = 60.0
SEARCH_HEARTBEAT_SECONDS = 10.0
_BINARY_EXTENSIONS = {
    ".7z", ".avi", ".bin", ".bmp", ".class", ".dll", ".dmg", ".doc",
    ".docx", ".exe", ".gif", ".gz", ".ico", ".jar", ".jpeg", ".jpg",
    ".mov", ".mp3", ".mp4", ".pdf", ".png", ".ppt", ".pptx", ".pyc",
    ".so", ".tar", ".tif", ".tiff", ".webp", ".xls", ".xlsx", ".zip",
}
_BLOCKED_POSIX_DEVICES = {
    "/dev/full", "/dev/null", "/dev/random", "/dev/stdin", "/dev/tty",
    "/dev/urandom", "/dev/zero",
}
_BLOCKED_WINDOWS_DEVICE_NAMES = {
    "aux", "clock$", "con", "nul", "prn",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _normalize_read_pagination(
    offset: int | None,
    limit: int | None,
) -> tuple[int, int]:
    """Return bounded 1-indexed pagination values."""
    normalized_offset = offset if isinstance(offset, int) and not isinstance(offset, bool) else 1
    normalized_limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else DEFAULT_READ_LIMIT
    return max(1, normalized_offset), max(1, min(normalized_limit, MAX_READ_LINES))


def _normalize_search_pagination(offset: int | None, limit: int | None) -> tuple[int, int]:
    normalized_offset = offset if isinstance(offset, int) and not isinstance(offset, bool) else 0
    normalized_limit = limit if isinstance(limit, int) and not isinstance(limit, bool) else DEFAULT_SEARCH_LIMIT
    return max(0, normalized_offset), max(1, min(normalized_limit, MAX_SEARCH_RESULTS))


def _blocked_device_error(file_path: Path) -> str | None:
    """Reject special device paths before performing any I/O."""
    normalized = file_path.as_posix().casefold()
    if normalized in _BLOCKED_POSIX_DEVICES or normalized.startswith("/dev/fd/"):
        return f"Cannot read device file: {file_path}"
    device_name = file_path.name.split(".", 1)[0].casefold().rstrip(":")
    if device_name in _BLOCKED_WINDOWS_DEVICE_NAMES:
        return f"Cannot read Windows device path: {file_path}"
    return None


def _binary_file_error(file_path: Path) -> str | None:
    """Return an actionable error for binary files, otherwise None."""
    suffix = file_path.suffix.casefold()
    if suffix in _BINARY_EXTENSIONS:
        if suffix in {".docx", ".xlsx", ".pptx", ".pdf"}:
            return (
                f"Cannot read structured binary file '{file_path.name}' with read_file. "
                "Use execute_code with the appropriate document library."
            )
        return f"Cannot read binary file '{file_path.name}' with read_file."
    try:
        with file_path.open("rb") as stream:
            sample = stream.read(8_192)
    except OSError:
        return None
    if b"\x00" in sample:
        return f"Cannot read binary file '{file_path.name}' with read_file."
    return None


def _similar_file_suggestions(file_path: Path, limit: int = 5) -> list[str]:
    """Return deterministic nearby filename suggestions for a missing path."""
    parent = file_path.parent
    try:
        candidates = [candidate for candidate in parent.iterdir() if candidate.is_file()]
    except OSError:
        return []
    wanted_name = file_path.name.casefold()
    wanted_stem = file_path.stem.casefold()

    def score(candidate: Path) -> tuple[int, str]:
        name = candidate.name.casefold()
        stem = candidate.stem.casefold()
        value = 0
        if stem == wanted_stem:
            value = 90
        elif name.startswith(wanted_name) or wanted_name.startswith(name):
            value = 70
        elif wanted_name in name or name in wanted_name:
            value = 60
        else:
            overlap = len(set(wanted_stem) & set(stem))
            value = overlap
        return value, candidate.name

    ranked = sorted(candidates, key=lambda candidate: (-score(candidate)[0], score(candidate)[1]))
    return [str(candidate) for candidate in ranked[:limit] if score(candidate)[0] > 0]


def _resolve_from_active_root(
    path: str,
    *,
    workspace_dir: Path,
    relative_root_dir: Path,
) -> Path:
    """Resolve canonical artifact paths and legacy workspace-relative paths."""
    file_path = Path(path)
    if file_path.is_absolute():
        return file_path

    try:
        root_from_workspace = relative_root_dir.relative_to(workspace_dir)
    except ValueError:
        root_from_workspace = None
    if (
        root_from_workspace
        and file_path.parts[: len(root_from_workspace.parts)] == root_from_workspace.parts
    ):
        return workspace_dir / file_path
    return relative_root_dir / file_path


def _strip_number_prefix(line: str) -> str:
    """Remove the read_file line-number prefix from one formatted line."""
    if "|" not in line:
        return line
    prefix, rest = line.split("|", 1)
    return rest if prefix.strip().isdigit() else line


def _cap_preview_lines(lines: list[str], max_chars: int = 1200) -> list[str]:
    """Keep preview snippets useful without retaining a large artifact body."""
    capped: list[str] = []
    used = 0
    for line in lines:
        remaining = max_chars - used
        if remaining <= 0:
            break
        if len(line) > remaining:
            capped.append(line[:remaining] + "...")
            used = max_chars
            break
        capped.append(line)
        used += len(line)
    return capped


def _looks_like_generated_artifact(file_path: Path, content: str) -> bool:
    """Return true for files that should not be retained verbatim in model history."""
    if is_model_instruction_source_path(file_path):
        return False
    suffix = file_path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return True
    if suffix in {".json", ".log"} and any(part in _MODEL_CONTEXT_PATH_PARTS for part in file_path.parts):
        return True
    if any(part in _MODEL_CONTEXT_PATH_PARTS for part in file_path.parts) and suffix in _MODEL_CONTEXT_EXTS:
        return True
    return len(content) > _MODEL_CONTEXT_SIZE_THRESHOLD and suffix in _MODEL_CONTEXT_EXTS


def _model_history_placeholder_error(*values: str) -> str | None:
    """Reject internal history placeholders before they reach real files."""
    for value in values:
        if is_model_history_placeholder(value):
            return (
                "Refusing to write a model-history placeholder to disk. "
                "Regenerate the real file content, or read the existing file with read_file before editing."
            )
    return None


def _oversized_file_tool_argument_error(tool_name: str, argument_name: str, value: str) -> str | None:
    """Reject large generated bodies before they encourage provider-side truncation."""
    if len(value) <= MAX_FILE_TOOL_CONTENT_CHARS:
        return None
    return (
        f"FILE_TOOL_ARGUMENT_TOO_LARGE: {tool_name}.{argument_name} is "
        f"{len(value)} characters; limit is {MAX_FILE_TOOL_CONTENT_CHARS}. "
        "For large generated artifacts such as HTML/CSS/JS, JSON manifests, "
        "templates, base64, or file bodies, split the work into smaller chunks. "
        "Use write_file for the first chunk and append_file for later chunks, "
        "then validate with read_file or a render check."
    )


def _summarize_json_for_model(raw_text: str) -> list[str]:
    """Extract a small, useful JSON summary without keeping the full payload."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return []

    lines: list[str] = []
    if isinstance(data, dict):
        keys = list(data.keys())
        lines.append(f"top_level_keys: {', '.join(map(str, keys[:20]))}")
        for key in ("ok", "success", "status", "error", "errors", "warning", "warnings", "slideCount", "slide_count"):
            if key in data:
                value = data[key]
                preview = json.dumps(value, ensure_ascii=False)
                if len(preview) > 500:
                    preview = preview[:500] + "..."
                lines.append(f"{key}: {preview}")
    elif isinstance(data, list):
        lines.append(f"array_length: {len(data)}")
        if data:
            preview = json.dumps(data[0], ensure_ascii=False)
            if len(preview) > 500:
                preview = preview[:500] + "..."
            lines.append(f"first_item: {preview}")
    return lines


def build_read_file_model_context(file_path: Path, content: str, total_lines: int) -> str | None:
    """Build a compact model-history substitute for generated or QA artifacts."""
    if not _looks_like_generated_artifact(file_path, content):
        return None

    raw_lines = [_strip_number_prefix(line) for line in content.splitlines()]
    raw_text = "\n".join(raw_lines)
    suffix = file_path.suffix.lower()
    summary_lines = [
        "[Full file content omitted from model history]",
        f"Tool: read_file",
        f"Path: {file_path}",
        f"Type: {suffix or 'unknown'}",
        f"Lines: {total_lines}",
        f"Characters: {len(raw_text)}",
        "Reason: generated/QA artifact content can bloat future LLM turns; read the file again with offset/limit if exact content is needed.",
    ]

    if suffix == ".json":
        json_summary = _summarize_json_for_model(raw_text)
        if json_summary:
            summary_lines.append("")
            summary_lines.append("JSON summary:")
            summary_lines.extend(f"- {line}" for line in json_summary)

    preview_limit = 20 if suffix not in {".html", ".htm"} else 12
    preview = _cap_preview_lines(raw_lines[:preview_limit])
    if preview:
        summary_lines.append("")
        summary_lines.append(f"Preview first {len(preview)} lines:")
        summary_lines.extend(preview)

    return "\n".join(summary_lines)


class ReadTool(Tool):
    """Read file content."""

    def __init__(
        self,
        workspace_dir: str = ".",
        allow_full_access: bool = True,
        permission_engine: PermissionEngine | None = None,
        relative_root_dir: str | None = None,
    ):
        """Initialize ReadTool with workspace directory.

        Args:
            workspace_dir: Security boundary for filesystem access
            allow_full_access: If False, restrict reads to workspace directory
            permission_engine: If provided, use capability-based permission checks
            relative_root_dir: Optional base directory for resolving relative paths
        """
        self.workspace_dir = Path(workspace_dir).absolute()
        self.relative_root_dir = (
            Path(relative_root_dir).absolute() if relative_root_dir else self.workspace_dir
        )
        self.allow_full_access = allow_full_access
        self._perm = permission_engine

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read a text file with line numbers and bounded pagination. Use this instead of "
            "cat/head/tail or shell commands that print file contents. Output uses "
            "'LINE_NUMBER|LINE_CONTENT' (1-indexed). The default page is 500 lines and the "
            "maximum is 2000; use offset and limit to continue through large files. "
            "Binary and structured document files are rejected with an actionable error. "
            "You can call this tool multiple times in parallel to read different files simultaneously."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (1-indexed, default: 1)",
                    "default": 1,
                    "minimum": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum lines to read (default: 500, max: 2000)",
                    "default": DEFAULT_READ_LIMIT,
                    "minimum": 1,
                    "maximum": MAX_READ_LINES,
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        """Execute read file."""
        try:
            offset, limit = _normalize_read_pagination(offset, limit)
            # Resolve relative paths from the active project/artifact root while
            # retaining workspace_dir as the filesystem security boundary.
            file_path = _resolve_from_active_root(
                path,
                workspace_dir=self.workspace_dir,
                relative_root_dir=self.relative_root_dir,
            )
            if not file_path.exists() and not Path(path).is_absolute():
                workspace_candidate = self.workspace_dir / path
                if workspace_candidate.exists():
                    file_path = workspace_candidate

            # Path validation
            if self._perm:
                decision = self._perm.check(
                    capability="filesystem.read",
                    resource={"path": str(file_path)},
                    tool_name=self.name,
                )
                if not decision.allowed:
                    return ToolResult(
                        success=False,
                        error=decision.reason,
                        permission_request=decision.permission_request,
                    )
            elif not self.allow_full_access:
                error = validate_path_in_workspace(file_path, self.workspace_dir)
                if error:
                    return ToolResult(success=False, content="", error=error)

            device_error = _blocked_device_error(file_path)
            if device_error:
                return ToolResult(success=False, content="", error=device_error)

            if not file_path.exists():
                suggestions = _similar_file_suggestions(file_path)
                suggestion_text = (
                    f" Did you mean: {', '.join(suggestions)}" if suggestions else ""
                )
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}.{suggestion_text}",
                )
            if not file_path.is_file():
                return ToolResult(
                    success=False,
                    content="",
                    error=(
                        f"Path is not a file: {path}. Use search_files with "
                        "target='files' to inspect a directory."
                    ),
                )

            binary_error = _binary_file_error(file_path)
            if binary_error:
                return ToolResult(success=False, content="", error=binary_error)

            # Count while retaining only the requested page. This keeps memory
            # bounded even when the source file is very large.
            start = offset - 1
            end = start + limit
            selected_lines: list[str] = []
            source_char_count = 0
            total_lines = 0
            replacement_seen = False
            with open(file_path, encoding="utf-8", errors="replace") as stream:
                for index, line in enumerate(stream):
                    total_lines = index + 1
                    source_char_count += len(line)
                    replacement_seen = replacement_seen or "\ufffd" in line
                    if start <= index < end:
                        selected_lines.append(line)

            selected_char_count = sum(len(line) for line in selected_lines)
            selected_line_count = len(selected_lines)

            if selected_char_count > MAX_READ_CHARS:
                return ToolResult(
                    success=False,
                    content="",
                    error=(
                        f"Read produced {selected_char_count:,} characters, exceeding the "
                        f"{MAX_READ_CHARS:,}-character safety limit. The file has "
                        f"{total_lines:,} lines. Retry with a smaller limit from offset={offset}."
                    ),
                    raw_output={
                        "source_char_count": source_char_count,
                        "selected_char_count": selected_char_count,
                        "selected_line_count": selected_line_count,
                        "total_lines": total_lines,
                        "truncated": False,
                    },
                )

            # Format with line numbers (1-indexed)
            numbered_lines: list[str] = []
            for i, line in enumerate(selected_lines, start=start + 1):
                # Remove trailing newline for formatting
                line_content = line.rstrip("\n")
                numbered_lines.append(f"{i:6d}|{line_content}")

            if replacement_seen:
                numbered_lines.insert(
                    0,
                    "[Warning: File contains non-UTF-8 bytes; invalid bytes were replaced with \ufffd.]",
                )
            content = "\n".join(numbered_lines)
            has_more = end < total_lines
            if has_more:
                next_offset = offset + selected_line_count
                content += (
                    f"\n\n[Hint: showing lines {offset}-{offset + selected_line_count - 1} "
                    f"of {total_lines}. Use offset={next_offset}, limit={limit} to continue.]"
                )

            model_context = build_read_file_model_context(file_path, content, total_lines)
            return ToolResult(
                success=True,
                content=content,
                model_context=model_context,
                raw_output={
                    "source_char_count": source_char_count,
                    "selected_char_count": selected_char_count,
                    "selected_line_count": selected_line_count,
                    "total_lines": total_lines,
                    "truncated": False,
                    "has_more": has_more,
                    "next_offset": offset + selected_line_count if has_more else None,
                },
            )
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class SearchFilesTool(EventEmittingTool):
    """Search file names or text content without routing through a shell."""

    parallel_safe = True
    cancel_on_agent_cancel = True

    def __init__(
        self,
        workspace_dir: str = ".",
        allow_full_access: bool = True,
        permission_engine: PermissionEngine | None = None,
        relative_root_dir: str | None = None,
        search_timeout_seconds: float = DEFAULT_SEARCH_TIMEOUT_SECONDS,
        heartbeat_seconds: float = SEARCH_HEARTBEAT_SECONDS,
    ):
        super().__init__()
        self.workspace_dir = Path(workspace_dir).absolute()
        self.relative_root_dir = (
            Path(relative_root_dir).absolute() if relative_root_dir else self.workspace_dir
        )
        self.allow_full_access = allow_full_access
        self._perm = permission_engine
        self.search_timeout_seconds = max(0.01, float(search_timeout_seconds))
        self.heartbeat_seconds = max(0.01, float(heartbeat_seconds))

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return (
            "Search file contents or find files by name. Use this instead of grep/rg/find/ls "
            "in bash. target='content' performs a regular-expression text search; "
            "target='files' finds files by glob pattern and is the correct way to inspect "
            "a directory. Results are bounded and support offset/limit pagination."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex for content search or glob pattern for file search",
                },
                "target": {
                    "type": "string",
                    "enum": ["content", "files"],
                    "default": "content",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search (default: active workspace root)",
                    "default": ".",
                },
                "file_glob": {
                    "type": "string",
                    "description": "Optional glob limiting files during content search",
                },
                "limit": {
                    "type": "integer",
                    "default": DEFAULT_SEARCH_LIMIT,
                    "minimum": 1,
                    "maximum": MAX_SEARCH_RESULTS,
                },
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_only", "count"],
                    "default": "content",
                },
                "context": {
                    "type": "integer",
                    "description": "Context lines before and after content matches (max: 10)",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 10,
                },
            },
            "required": ["pattern"],
        }

    def _resolve_path(self, path: str) -> Path:
        search_path = _resolve_from_active_root(
            path,
            workspace_dir=self.workspace_dir,
            relative_root_dir=self.relative_root_dir,
        )
        if not search_path.exists() and not Path(path).is_absolute():
            workspace_candidate = self.workspace_dir / path
            if workspace_candidate.exists():
                return workspace_candidate
        return search_path

    def _permission_error(self, search_path: Path) -> ToolResult | None:
        if self._perm:
            decision = self._perm.check(
                capability="filesystem.read",
                resource={"path": str(search_path)},
                tool_name=self.name,
            )
            if not decision.allowed:
                return ToolResult(
                    success=False,
                    error=decision.reason,
                    permission_request=decision.permission_request,
                )
        elif not self.allow_full_access:
            error = validate_path_in_workspace(search_path, self.workspace_dir)
            if error:
                return ToolResult(success=False, error=error)
        return None

    async def execute_with_event_context(
        self,
        *,
        event_queue: asyncio.Queue,
        parent_tool_call_id: str,
        **kwargs: Any,
    ) -> ToolResult:
        """Use per-call event state so parallel searches cannot race."""
        return await self.execute(
            **kwargs,
            _event_queue=event_queue,
            _parent_tool_call_id=parent_tool_call_id,
        )

    def _iter_files(
        self,
        search_path: Path,
        *,
        stop_event: threading.Event,
        deadline: float,
    ) -> Iterator[Path]:
        if search_path.is_file():
            if not stop_event.is_set() and time.monotonic() < deadline:
                yield search_path
            return
        for current_root, directories, filenames in os.walk(search_path, followlinks=False):
            if stop_event.is_set() or time.monotonic() >= deadline:
                return
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in {".git", ".hg", ".svn", "node_modules", "__pycache__"}
            )
            root_path = Path(current_root)
            for filename in sorted(filenames):
                if stop_event.is_set() or time.monotonic() >= deadline:
                    return
                yield root_path / filename

    def _file_allowed(self, file_path: Path) -> bool:
        if not self._perm:
            return True
        return self._perm.check(
            capability="filesystem.read",
            resource={"path": str(file_path)},
            tool_name=self.name,
        ).allowed

    @staticmethod
    def _line_text(line: str) -> str:
        return line if len(line) <= 2_000 else line[:2_000] + "... [line truncated]"

    def _search_sync(
        self,
        *,
        pattern: str,
        target: str,
        search_path: Path,
        file_glob: str | None,
        limit: int,
        offset: int,
        output_mode: str,
        context: int,
        stop_event: threading.Event,
        deadline: float,
    ) -> dict[str, Any]:
        """Run a cooperative, streaming search outside the asyncio loop."""
        expression = re.compile(pattern) if target == "content" else None
        base = search_path if search_path.is_dir() else search_path.parent
        required_results = offset + limit
        matches: list[str] = []
        counts: dict[str, int] = {}
        seen_files: set[str] = set()
        scanned_files = 0
        matched_results = 0
        has_more = False

        def stopped() -> bool:
            return stop_event.is_set() or time.monotonic() >= deadline

        def add_result(value: str) -> bool:
            """Keep only the requested prefix and stop after one extra match."""
            nonlocal matched_results, has_more
            matched_results += 1
            if len(matches) < required_results:
                matches.append(value)
                return False
            has_more = True
            return True

        for file_path in self._iter_files(
            search_path,
            stop_event=stop_event,
            deadline=deadline,
        ):
            if stopped():
                break
            if not self._file_allowed(file_path):
                continue
            scanned_files += 1
            relative = file_path.relative_to(base).as_posix()

            if target == "files":
                if fnmatch(file_path.name, pattern) or fnmatch(relative, pattern):
                    if add_result(relative):
                        break
                continue

            if file_glob and not (
                fnmatch(file_path.name, file_glob) or fnmatch(relative, file_glob)
            ):
                continue
            if _binary_file_error(file_path):
                continue

            try:
                if context > 0:
                    # Context rendering needs neighbouring lines, but remains
                    # bounded to one file rather than retaining the whole tree.
                    lines = file_path.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    line_source = enumerate(lines)
                else:
                    lines = None
                    stream = file_path.open(encoding="utf-8", errors="replace")
                    line_source = enumerate(stream)

                try:
                    for line_index, raw_line in line_source:
                        if stopped():
                            break
                        line = raw_line.rstrip("\r\n")
                        if expression is None or not expression.search(line):
                            continue
                        counts[relative] = counts.get(relative, 0) + 1
                        if output_mode == "count":
                            continue
                        if output_mode == "files_only":
                            if relative in seen_files:
                                continue
                            seen_files.add(relative)
                            if add_result(relative):
                                break
                            continue

                        if lines is None:
                            rendered = f"{relative}:{line_index + 1}:>{self._line_text(line)}"
                        else:
                            first = max(0, line_index - context)
                            last = min(len(lines), line_index + context + 1)
                            rendered_lines = []
                            for context_index in range(first, last):
                                marker = ">" if context_index == line_index else " "
                                rendered_lines.append(
                                    f"{relative}:{context_index + 1}:{marker}"
                                    f"{self._line_text(lines[context_index])}"
                                )
                            rendered = "\n".join(rendered_lines)
                        if add_result(rendered):
                            break
                finally:
                    if lines is None:
                        stream.close()
            except OSError:
                continue

            if has_more and output_mode != "count":
                break

        timed_out = not stop_event.is_set() and time.monotonic() >= deadline
        if output_mode == "count" and target == "content":
            matches = [f"{relative}:{count}" for relative, count in sorted(counts.items())]
            matched_results = len(matches)
            selected = matches[offset : offset + limit]
            has_more = len(matches) > offset + limit
            exact_total = not timed_out
        else:
            selected = matches[offset : offset + limit]
            exact_total = not has_more and not timed_out

        return {
            "selected": selected,
            "matched_results": matched_results,
            "scanned_files": scanned_files,
            "has_more": has_more,
            "timed_out": timed_out,
            "cancelled": stop_event.is_set(),
            "exact_total": exact_total,
        }

    async def execute(
        self,
        pattern: str,
        target: str = "content",
        path: str = ".",
        file_glob: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        output_mode: str = "content",
        context: int = 0,
        *,
        _event_queue: asyncio.Queue | None = None,
        _parent_tool_call_id: str | None = None,
    ) -> ToolResult:
        """Execute a bounded file-name or content search."""
        try:
            if not isinstance(pattern, str) or not pattern:
                return ToolResult(success=False, error="search_files requires a non-empty pattern")
            if target not in {"content", "files"}:
                return ToolResult(success=False, error="target must be 'content' or 'files'")
            if output_mode not in {"content", "files_only", "count"}:
                return ToolResult(success=False, error="Invalid output_mode")
            offset, limit = _normalize_search_pagination(offset, limit)
            context = max(0, min(context if isinstance(context, int) else 0, 10))
            search_path = self._resolve_path(path)
            denied = self._permission_error(search_path)
            if denied:
                return denied
            if not search_path.exists():
                return ToolResult(success=False, error=f"Search path not found: {path}")

            if target == "content":
                try:
                    re.compile(pattern)
                except re.error as exc:
                    return ToolResult(success=False, error=f"Invalid search regex: {exc}")

            stop_event = threading.Event()
            deadline = time.monotonic() + self.search_timeout_seconds
            worker = asyncio.create_task(
                asyncio.to_thread(
                    self._search_sync,
                    pattern=pattern,
                    target=target,
                    search_path=search_path,
                    file_glob=file_glob,
                    limit=limit,
                    offset=offset,
                    output_mode=output_mode,
                    context=context,
                    stop_event=stop_event,
                    deadline=deadline,
                )
            )
            queue = _event_queue if _event_queue is not None else self._event_queue
            try:
                scan: dict[str, Any] | None = None
                while not worker.done():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        stop_event.set()
                        worker.cancel()
                        scan = {
                            "selected": [],
                            "matched_results": 0,
                            "scanned_files": 0,
                            "has_more": False,
                            "timed_out": True,
                            "cancelled": False,
                            "exact_total": False,
                        }
                        break
                    done, _pending = await asyncio.wait(
                        {worker}, timeout=min(self.heartbeat_seconds, remaining)
                    )
                    if done:
                        break
                    if queue is not None:
                        queue.put_nowait(
                            ProgressEvent(
                                step=0,
                                content=(
                                    f"search_files is still scanning {search_path}; "
                                    "the search remains cancellable."
                                ),
                            )
                        )
                if scan is None:
                    scan = await worker
            except asyncio.CancelledError:
                stop_event.set()
                worker.cancel()
                raise

            selected = scan["selected"]
            truncated = scan["has_more"] or scan["timed_out"]
            content = "\n".join(selected)
            if not content:
                content = (
                    f"Search timed out after {self.search_timeout_seconds:g} seconds before "
                    "finding a match. Narrow the path, pattern, or file_glob."
                    if scan["timed_out"]
                    else "No matches found."
                )
            if scan["has_more"]:
                content += (
                    f"\n\n[Hint: showing results {offset + 1}-{offset + len(selected)} "
                    f"with more available. Use offset={offset + limit}, limit={limit} to continue.]"
                )
            if scan["timed_out"] and selected:
                content += (
                    f"\n\n[Warning: search timed out after {self.search_timeout_seconds:g} seconds. "
                    "Partial results are shown; narrow the search before retrying.]"
                )
            return ToolResult(
                success=True,
                content=content,
                raw_output={
                    "target": target,
                    "path": str(search_path),
                    "total_matches": (
                        scan["matched_results"] if scan["exact_total"] else None
                    ),
                    "matched_through": scan["matched_results"],
                    "total_is_exact": scan["exact_total"],
                    "returned_matches": len(selected),
                    "truncated": truncated,
                    "next_offset": offset + limit if truncated else None,
                    "scanned_files": scan["scanned_files"],
                    "timed_out": scan["timed_out"],
                    "limit_reason": "search_timeout" if scan["timed_out"] else None,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, content="", error=str(exc))


class WriteTool(Tool):
    """Write content to a file."""

    def __init__(
        self,
        workspace_dir: str = ".",
        allow_full_access: bool = True,
        permission_engine: PermissionEngine | None = None,
        relative_root_dir: str | None = None,
    ):
        """Initialize WriteTool with workspace directory.

        Args:
            workspace_dir: Security boundary for filesystem access
            allow_full_access: If False, restrict writes to workspace directory
            permission_engine: If provided, use capability-based permission checks
            relative_root_dir: Optional base directory for resolving relative paths
        """
        self.workspace_dir = Path(workspace_dir).absolute()
        self.relative_root_dir = (
            Path(relative_root_dir).absolute() if relative_root_dir else self.workspace_dir
        )
        self.allow_full_access = allow_full_access
        self._perm = permission_engine

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "Write content to a file. Will overwrite existing files completely. "
            "For existing files, you should read the file first using read_file. "
            "Prefer editing existing files over creating new ones unless explicitly needed. "
            f"Keep content under {MAX_FILE_TOOL_CONTENT_CHARS_DISPLAY} characters; "
            "for larger generated artifacts, write the first chunk with write_file "
            "and continue with append_file."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "content": {
                    "type": "string",
                    "maxLength": MAX_FILE_TOOL_CONTENT_CHARS,
                    "description": (
                        "Complete content to write (will replace existing content). "
                        f"Keep this under {MAX_FILE_TOOL_CONTENT_CHARS_DISPLAY} "
                        "characters. For large generated artifacts such as HTML/CSS/JS, "
                        "JSON manifests, templates, base64, or file bodies, use "
                        "write_file for the first chunk and append_file for later "
                        "chunks, then validate."
                    ),
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> ToolResult:
        """Execute write file."""
        try:
            # Resolve relative paths from the active project/artifact root.
            file_path = _resolve_from_active_root(
                path,
                workspace_dir=self.workspace_dir,
                relative_root_dir=self.relative_root_dir,
            )

            # Path validation
            if self._perm:
                decision = self._perm.check(
                    capability="filesystem.write",
                    resource={"path": str(file_path)},
                    tool_name=self.name,
                )
                if not decision.allowed:
                    return ToolResult(
                        success=False,
                        error=decision.reason,
                        permission_request=decision.permission_request,
                    )
            elif not self.allow_full_access:
                error = validate_path_in_workspace(file_path, self.workspace_dir)
                if error:
                    return ToolResult(success=False, content="", error=error)

            placeholder_error = _model_history_placeholder_error(content)
            if placeholder_error:
                return ToolResult(success=False, content="", error=placeholder_error)

            size_error = _oversized_file_tool_argument_error(self.name, "content", content)
            if size_error:
                return ToolResult(success=False, content="", error=size_error)

            bypass_error = detect_pptx_self_check_bypass(str(file_path), content)
            if bypass_error:
                return ToolResult(success=False, content="", error=bypass_error)

            # Backup existing file before overwrite
            backup_file(file_path)

            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content, encoding="utf-8")
            return ToolResult(success=True, content=f"Successfully wrote to {file_path}")
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class AppendTool(Tool):
    """Append content to a file."""

    def __init__(
        self,
        workspace_dir: str = ".",
        allow_full_access: bool = True,
        permission_engine: PermissionEngine | None = None,
        relative_root_dir: str | None = None,
    ):
        """Initialize AppendTool with workspace directory."""
        self.workspace_dir = Path(workspace_dir).absolute()
        self.relative_root_dir = (
            Path(relative_root_dir).absolute() if relative_root_dir else self.workspace_dir
        )
        self.allow_full_access = allow_full_access
        self._perm = permission_engine

    @property
    def name(self) -> str:
        return "append_file"

    @property
    def description(self) -> str:
        return (
            "Append content to a file, creating it if it does not exist. "
            f"Keep each content chunk under {MAX_FILE_TOOL_CONTENT_CHARS_DISPLAY} "
            "characters. Use after write_file for large generated artifacts such "
            "as HTML/CSS/JS, JSON manifests, templates, base64, or file bodies."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "content": {
                    "type": "string",
                    "maxLength": MAX_FILE_TOOL_CONTENT_CHARS,
                    "description": (
                        "Content chunk to append. Keep this under "
                        f"{MAX_FILE_TOOL_CONTENT_CHARS_DISPLAY} characters. "
                        "For large generated artifacts, split the file into "
                        "multiple append_file calls and validate the final file."
                    ),
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> ToolResult:
        """Execute append file."""
        try:
            file_path = _resolve_from_active_root(
                path,
                workspace_dir=self.workspace_dir,
                relative_root_dir=self.relative_root_dir,
            )

            if self._perm:
                decision = self._perm.check(
                    capability="filesystem.write",
                    resource={"path": str(file_path)},
                    tool_name=self.name,
                )
                if not decision.allowed:
                    return ToolResult(
                        success=False,
                        error=decision.reason,
                        permission_request=decision.permission_request,
                    )
            elif not self.allow_full_access:
                error = validate_path_in_workspace(file_path, self.workspace_dir)
                if error:
                    return ToolResult(success=False, content="", error=error)

            placeholder_error = _model_history_placeholder_error(content)
            if placeholder_error:
                return ToolResult(success=False, content="", error=placeholder_error)

            size_error = _oversized_file_tool_argument_error(self.name, "content", content)
            if size_error:
                return ToolResult(success=False, content="", error=size_error)

            existing = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
            bypass_error = detect_pptx_self_check_bypass(str(file_path), f"{existing}\n{content}")
            if bypass_error:
                return ToolResult(success=False, content="", error=bypass_error)

            backup_file(file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("a", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(success=True, content=f"Successfully appended to {file_path}")
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class EditTool(Tool):
    """Edit file by replacing text."""

    def __init__(
        self,
        workspace_dir: str = ".",
        allow_full_access: bool = True,
        permission_engine: PermissionEngine | None = None,
        relative_root_dir: str | None = None,
    ):
        """Initialize EditTool with workspace directory.

        Args:
            workspace_dir: Security boundary for filesystem access
            allow_full_access: If False, restrict edits to workspace directory
            permission_engine: If provided, use capability-based permission checks
            relative_root_dir: Optional base directory for resolving relative paths
        """
        self.workspace_dir = Path(workspace_dir).absolute()
        self.relative_root_dir = (
            Path(relative_root_dir).absolute() if relative_root_dir else self.workspace_dir
        )
        self.allow_full_access = allow_full_access
        self._perm = permission_engine

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "Perform exact string replacement in a file. The old_str must match exactly "
            "and appear uniquely in the file, otherwise the operation will fail. "
            "You must read the file first before editing. Preserve exact indentation from the source."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative path to the file",
                },
                "old_str": {
                    "type": "string",
                    "description": "Exact string to find and replace (must be unique in file)",
                },
                "new_str": {
                    "type": "string",
                    "description": "Replacement string (use for refactoring, renaming, etc.)",
                },
            },
            "required": ["path", "old_str", "new_str"],
        }

    async def execute(self, path: str, old_str: str, new_str: str) -> ToolResult:
        """Execute edit file."""
        try:
            # Resolve relative paths from the active project/artifact root.
            file_path = _resolve_from_active_root(
                path,
                workspace_dir=self.workspace_dir,
                relative_root_dir=self.relative_root_dir,
            )
            if not file_path.exists() and not Path(path).is_absolute():
                workspace_candidate = self.workspace_dir / path
                if workspace_candidate.exists():
                    file_path = workspace_candidate

            # Path validation
            if self._perm:
                decision = self._perm.check(
                    capability="filesystem.write",
                    resource={"path": str(file_path)},
                    tool_name=self.name,
                )
                if not decision.allowed:
                    return ToolResult(
                        success=False,
                        error=decision.reason,
                        permission_request=decision.permission_request,
                    )
            elif not self.allow_full_access:
                error = validate_path_in_workspace(file_path, self.workspace_dir)
                if error:
                    return ToolResult(success=False, content="", error=error)

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}",
                )

            content = file_path.read_text(encoding="utf-8")

            placeholder_error = _model_history_placeholder_error(old_str, new_str)
            if placeholder_error:
                return ToolResult(success=False, content="", error=placeholder_error)

            bypass_error = detect_pptx_self_check_bypass(str(file_path), f"{content}\n{old_str}\n{new_str}")
            if bypass_error:
                return ToolResult(success=False, content="", error=bypass_error)

            if old_str not in content:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Text not found in file: {old_str}",
                )

            # Backup before editing
            backup_file(file_path)

            new_content = content.replace(old_str, new_str)
            file_path.write_text(new_content, encoding="utf-8")

            return ToolResult(success=True, content=f"Successfully edited {file_path}")
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))
