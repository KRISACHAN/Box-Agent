"""File operation tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import tiktoken

from .base import Tool, ToolResult
from .pptx_safety import detect_pptx_self_check_bypass
from .safety import backup_file, validate_path_in_workspace

if TYPE_CHECKING:
    from .permissions import PermissionEngine


def truncate_text_by_tokens(
    text: str,
    max_tokens: int,
) -> str:
    """Truncate text by token count if it exceeds the limit.

    When text exceeds the specified token limit, performs intelligent truncation
    by keeping the front and back parts while truncating the middle.

    Args:
        text: Text to be truncated
        max_tokens: Maximum token limit

    Returns:
        str: Truncated text if it exceeds the limit, otherwise the original text.

    Example:
        >>> text = "very long text..." * 10000
        >>> truncated = truncate_text_by_tokens(text, 64000)
        >>> print(truncated)
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    token_count = len(encoding.encode(text))

    # Return original text if under limit
    if token_count <= max_tokens:
        return text

    # Calculate token/character ratio for approximation
    char_count = len(text)
    ratio = token_count / char_count

    # Keep head and tail mode: allocate half space for each (with 5% safety margin)
    chars_per_half = int((max_tokens / 2) / ratio * 0.95)

    # Truncate front part: find nearest newline
    head_part = text[:chars_per_half]
    last_newline_head = head_part.rfind("\n")
    if last_newline_head > 0:
        head_part = head_part[:last_newline_head]

    # Truncate back part: find nearest newline
    tail_part = text[-chars_per_half:]
    first_newline_tail = tail_part.find("\n")
    if first_newline_tail > 0:
        tail_part = tail_part[first_newline_tail + 1 :]

    # Combine result
    truncation_note = f"\n\n... [Content truncated: {token_count} tokens -> ~{max_tokens} tokens limit] ...\n\n"
    return head_part + truncation_note + tail_part


_MODEL_CONTEXT_EXTS = {".html", ".htm", ".json", ".md", ".txt", ".log", ".xml"}
_MODEL_CONTEXT_PATH_PARTS = {"qa", "rendered", "slides", "vision_inputs"}
_MODEL_CONTEXT_SIZE_THRESHOLD = 8_000
MAX_FILE_TOOL_CONTENT_CHARS = 8_000
MAX_FILE_TOOL_CONTENT_CHARS_DISPLAY = f"{MAX_FILE_TOOL_CONTENT_CHARS:,}"
_MODEL_HISTORY_PLACEHOLDER_PREFIXES = (
    "[Full tool-call argument omitted from model history]",
    "[Full file content omitted from model history]",
    "[Full tool output omitted from model history]",
)


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
        if any(value.startswith(prefix) for prefix in _MODEL_HISTORY_PLACEHOLDER_PREFIXES):
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

    def __init__(self, workspace_dir: str = ".", allow_full_access: bool = True,
                 permission_engine: PermissionEngine | None = None):
        """Initialize ReadTool with workspace directory.

        Args:
            workspace_dir: Base directory for resolving relative paths
            allow_full_access: If False, restrict reads to workspace directory
            permission_engine: If provided, use capability-based permission checks
        """
        self.workspace_dir = Path(workspace_dir).absolute()
        self.allow_full_access = allow_full_access
        self._perm = permission_engine

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "Read file contents from the filesystem. Output always includes line numbers "
            "in format 'LINE_NUMBER|LINE_CONTENT' (1-indexed). Supports reading partial content "
            "by specifying line offset and limit for large files. "
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
                    "description": "Starting line number (1-indexed). Use for large files to read from specific line",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of lines to read. Use with offset for large files to read in chunks",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, offset: int | None = None, limit: int | None = None) -> ToolResult:
        """Execute read file."""
        try:
            file_path = Path(path)
            # Resolve relative paths relative to workspace_dir
            if not file_path.is_absolute():
                file_path = self.workspace_dir / file_path

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

            if not file_path.exists():
                return ToolResult(
                    success=False,
                    content="",
                    error=f"File not found: {path}",
                )

            # Read file content with line numbers
            try:
                with open(file_path, encoding="utf-8") as f:
                    lines = f.readlines()
            except UnicodeDecodeError:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                # Prepend a warning that will appear before the content
                lines.insert(0, "[Warning: File contains non-UTF-8 bytes, some characters replaced with \ufffd. "
                              "For data files, consider using execute_code with pd.read_csv() or pd.read_excel().]\n")

            # Apply offset and limit
            start = (offset - 1) if offset else 0
            end = (start + limit) if limit else len(lines)
            if start < 0:
                start = 0
            if end > len(lines):
                end = len(lines)

            selected_lines = lines[start:end]

            # Format with line numbers (1-indexed)
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start + 1):
                # Remove trailing newline for formatting
                line_content = line.rstrip("\n")
                numbered_lines.append(f"{i:6d}|{line_content}")

            content = "\n".join(numbered_lines)

            # Apply token truncation if needed
            max_tokens = 32000
            content = truncate_text_by_tokens(content, max_tokens)

            model_context = build_read_file_model_context(file_path, content, len(lines))
            return ToolResult(success=True, content=content, model_context=model_context)
        except Exception as e:
            return ToolResult(success=False, content="", error=str(e))


class WriteTool(Tool):
    """Write content to a file."""

    def __init__(self, workspace_dir: str = ".", allow_full_access: bool = True,
                 permission_engine: PermissionEngine | None = None):
        """Initialize WriteTool with workspace directory.

        Args:
            workspace_dir: Base directory for resolving relative paths
            allow_full_access: If False, restrict writes to workspace directory
            permission_engine: If provided, use capability-based permission checks
        """
        self.workspace_dir = Path(workspace_dir).absolute()
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
            file_path = Path(path)
            # Resolve relative paths relative to workspace_dir
            if not file_path.is_absolute():
                file_path = self.workspace_dir / file_path

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

    def __init__(self, workspace_dir: str = ".", allow_full_access: bool = True,
                 permission_engine: PermissionEngine | None = None):
        """Initialize AppendTool with workspace directory."""
        self.workspace_dir = Path(workspace_dir).absolute()
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
            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.workspace_dir / file_path

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

    def __init__(self, workspace_dir: str = ".", allow_full_access: bool = True,
                 permission_engine: PermissionEngine | None = None):
        """Initialize EditTool with workspace directory.

        Args:
            workspace_dir: Base directory for resolving relative paths
            allow_full_access: If False, restrict edits to workspace directory
            permission_engine: If provided, use capability-based permission checks
        """
        self.workspace_dir = Path(workspace_dir).absolute()
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
            file_path = Path(path)
            # Resolve relative paths relative to workspace_dir
            if not file_path.is_absolute():
                file_path = self.workspace_dir / file_path

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
