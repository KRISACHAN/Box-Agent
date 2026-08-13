"""Best-effort per-session JSONL execution traces.

The trace path is deliberately independent from the human-readable agent log.
Trace failures are swallowed so observability can never change agent behavior.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import AsyncIterator, Mapping
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, TypeVar

from .llm.debug_logging import sanitize_for_logging

logger = logging.getLogger(__name__)

_TRACE_SCHEMA_VERSION = "box-agent-session-trace/v1"
_TRACE_CONTEXT: ContextVar[tuple["SessionTraceWriter", str] | None] = ContextVar(
    "box_agent_session_trace", default=None
)
_WRITE_LOCK = threading.Lock()
_FALSE_VALUES = {"0", "false", "no", "off"}
_SAFE_FILE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_T = TypeVar("_T")


def session_trace_enabled() -> bool:
    """Return whether durable session traces are enabled.

    Tracing is on by default for product diagnostics. It can be disabled for
    privacy-sensitive environments with ``BOX_AGENT_SESSION_TRACE_ENABLED=0``.
    """

    value = os.environ.get("BOX_AGENT_SESSION_TRACE_ENABLED")
    return value is None or value.strip().lower() not in _FALSE_VALUES


def default_session_trace_dir() -> Path:
    configured = os.environ.get("BOX_AGENT_SESSION_TRACE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".box-agent" / "log" / "sessions"


def safe_session_trace_name(session_id: str) -> str:
    """Build a stable filename without changing the recorded session id."""

    normalized = session_id.strip() or "unknown-session"
    safe = _SAFE_FILE_CHARS.sub("_", normalized).strip("._-")
    if not safe:
        safe = "session"
    if safe != normalized or len(safe) > 120:
        safe = f"{safe[:100]}-{sha256(normalized.encode('utf-8')).hexdigest()[:12]}"
    return f"{safe}.jsonl"


def _trace_value(value: Any) -> Any:
    """Return a full JSON-safe value while redacting credential-like keys."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            result.update(sanitize_for_logging({str(key): _trace_value(item)}))
        return result
    if isinstance(value, list | tuple):
        return [_trace_value(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return sanitize_for_logging(value.model_dump(exclude_none=True))
        except Exception:
            pass
    if hasattr(value, "to_schema"):
        try:
            return sanitize_for_logging(value.to_schema())
        except Exception:
            pass
    return sanitize_for_logging(value)


class SessionTraceWriter:
    """Append standalone JSON records to one file for one product session."""

    def __init__(
        self,
        *,
        session_id: str,
        acp_session_id: str,
        trace_dir: str | Path | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.session_id = session_id.strip() or acp_session_id.strip() or "unknown-session"
        self.acp_session_id = acp_session_id.strip()
        self.enabled = session_trace_enabled() if enabled is None else enabled
        self.trace_dir = Path(trace_dir) if trace_dir is not None else default_session_trace_dir()
        self.file_path = self.trace_dir / safe_session_trace_name(self.session_id)

    def write(
        self,
        event: str,
        *,
        turn_id: str = "",
        step: int | None = None,
        llm_call_id: str | None = None,
        tool_call_id: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        """Append one trace record; never raise into the caller."""

        if not self.enabled:
            return
        try:
            record: dict[str, Any] = {
                "schema_version": _TRACE_SCHEMA_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
                    "+00:00", "Z"
                ),
                "event": event,
                "session_id": self.session_id,
                "acp_session_id": self.acp_session_id,
                "turn_id": turn_id,
            }
            if step is not None:
                record["step"] = step
            if llm_call_id:
                record["llm_call_id"] = llm_call_id
            if tool_call_id:
                record["tool_call_id"] = tool_call_id
            if data is not None:
                record["data"] = _trace_value(dict(data))

            line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
            with _WRITE_LOCK:
                self.trace_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    self.file_path,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                    0o600,
                )
                with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                    handle.flush()
        except Exception:
            logger.debug("session trace write failed", exc_info=True)


def set_session_trace_writer(
    writer: SessionTraceWriter,
    *,
    turn_id: str,
) -> Token[tuple[SessionTraceWriter, str] | None]:
    """Bind a writer to the current turn and inherited async tasks."""

    return _TRACE_CONTEXT.set((writer, turn_id))


def reset_session_trace_writer(token: Token[tuple[SessionTraceWriter, str] | None]) -> None:
    _TRACE_CONTEXT.reset(token)


def emit_session_trace(
    event: str,
    *,
    turn_id: str = "",
    step: int | None = None,
    llm_call_id: str | None = None,
    tool_call_id: str | None = None,
    data: Mapping[str, Any] | None = None,
) -> None:
    """Write through the active trace context, if one exists."""

    context = _TRACE_CONTEXT.get()
    if context is None:
        return
    writer, context_turn_id = context
    writer.write(
        event,
        turn_id=turn_id.strip() or context_turn_id,
        step=step,
        llm_call_id=llm_call_id,
        tool_call_id=tool_call_id,
        data=data,
    )


async def scoped_session_trace(
    events: AsyncIterator[_T],
    *,
    writer: SessionTraceWriter,
    turn_id: str,
) -> AsyncIterator[_T]:
    """Iterate events with tracing bound, preserving the original event stream.

    Bind only while advancing or closing the wrapped iterator.  Keeping a
    ``ContextVar`` token active across ``yield`` is unsafe because Python may
    finalize an abandoned async generator in a different task context.
    """

    iterator = events.__aiter__()
    try:
        while True:
            token = set_session_trace_writer(writer, turn_id=turn_id)
            try:
                event = await anext(iterator)
            except StopAsyncIteration:
                return
            finally:
                reset_session_trace_writer(token)
            yield event
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            token = set_session_trace_writer(writer, turn_id=turn_id)
            try:
                await close()
            finally:
                reset_session_trace_writer(token)
