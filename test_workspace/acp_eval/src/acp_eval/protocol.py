"""Raw-first ACP protocol capture and observed-field aggregation."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from acp_eval.storage import append_jsonl, append_raw


@dataclass(frozen=True)
class ProtocolParseError:
    byte_offset: int
    error: str
    raw_size: int


class ProtocolRecorder:
    """Persist ACP frames before creating normalized protocol entries."""

    def __init__(
        self,
        attempt_dir: Path,
        wall_clock: Callable[[], datetime],
        monotonic_ns: Callable[[], int],
    ) -> None:
        self.attempt_dir = Path(attempt_dir)
        self.wall_clock = wall_clock
        self.monotonic_ns = monotonic_ns
        self._sequence = 0
        self._stdout_offset = 0
        self._parse_errors: list[ProtocolParseError] = []

    @property
    def parse_errors(self) -> tuple[ProtocolParseError, ...]:
        return tuple(self._parse_errors)

    @property
    def protocol_path(self) -> Path:
        return self.attempt_dir / "protocol.jsonl"

    def _record_message(self, direction: str, message: Mapping[str, Any]) -> None:
        self._sequence += 1
        append_jsonl(
            self.protocol_path,
            {
                "sequence": self._sequence,
                "direction": direction,
                "timestamp": self.wall_clock().isoformat(),
                "monotonic_ns": self.monotonic_ns(),
                "message": dict(message),
            },
        )

    def record_sent(self, message: Mapping[str, Any]) -> bytes:
        raw_message = json.dumps(
            dict(message), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8") + b"\n"
        append_raw(self.attempt_dir / "acp-stdin.raw", raw_message)
        self._record_message("sent", message)
        return raw_message

    def record_received_chunk(self, data: bytes) -> int:
        """Persist stdout bytes immediately and return their starting offset."""

        byte_offset = self._stdout_offset
        append_raw(self.attempt_dir / "acp-stdout.raw", data)
        self._stdout_offset += len(data)
        return byte_offset

    def record_persisted_received(
        self, raw_line: bytes, byte_offset: int
    ) -> dict[str, Any] | None:
        """Parse a complete frame whose bytes have already been persisted."""

        try:
            decoded = json.loads(raw_line.decode("utf-8"))
            if not isinstance(decoded, Mapping):
                raise ValueError("expected a JSON object")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self._parse_errors.append(
                ProtocolParseError(
                    byte_offset=byte_offset,
                    error=str(error),
                    raw_size=len(raw_line),
                )
            )
            return None

        message = dict(decoded)
        self._record_message("received", message)
        return message

    def record_incomplete_received(self, raw_data: bytes, byte_offset: int) -> None:
        """Record an unterminated frame already present in the raw stream."""

        self._parse_errors.append(
            ProtocolParseError(
                byte_offset=byte_offset,
                error="unterminated ACP stdout frame",
                raw_size=len(raw_data),
            )
        )

    def record_received(self, raw_line: bytes) -> dict[str, Any] | None:
        byte_offset = self.record_received_chunk(raw_line)
        return self.record_persisted_received(raw_line, byte_offset)


class ACPAccumulator:
    """Collect ACP fields exactly as observed, without judging task outcome."""

    def __init__(self) -> None:
        self.permission_request_count = 0
        self._assistant_chunks: list[str] = []
        self.token_usage: dict[str, Any] | None = None
        self.final_response: dict[str, Any] | None = None
        self.final_response_metadata: dict[str, Any] | None = None

    @property
    def assistant_text(self) -> str:
        return "".join(self._assistant_chunks)

    def consume(self, message: Mapping[str, Any]) -> None:
        if message.get("method") == "session/request_permission":
            self.permission_request_count += 1

        self._consume_message_chunk(message)
        self._consume_usage(message)
        self._consume_final_response(message)

    def _consume_message_chunk(self, message: Mapping[str, Any]) -> None:
        params = message.get("params")
        if not isinstance(params, Mapping):
            return
        update = params.get("update")
        if not isinstance(update, Mapping):
            return
        if update.get("sessionUpdate") != "agent_message_chunk":
            return
        self._assistant_chunks.extend(self._text_parts(update.get("content")))

    def _consume_usage(self, value: Any) -> None:
        if isinstance(value, Mapping):
            if value.get("type") == "turn_usage":
                usage = value.get("tokenUsage")
                if isinstance(usage, Mapping):
                    self.token_usage = dict(usage)
            for child in value.values():
                self._consume_usage(child)
        elif isinstance(value, list):
            for child in value:
                self._consume_usage(child)

    def _consume_final_response(self, message: Mapping[str, Any]) -> None:
        result = message.get("result")
        if not isinstance(result, Mapping) or "stopReason" not in result:
            return
        self.final_response = dict(message)
        metadata = result.get("_meta", result.get("field_meta"))
        self.final_response_metadata = (
            dict(metadata) if isinstance(metadata, Mapping) else None
        )

    @classmethod
    def _text_parts(cls, content: Any) -> list[str]:
        if isinstance(content, str):
            return [content]
        if isinstance(content, Mapping):
            text = content.get("text")
            return [text] if isinstance(text, str) else []
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                parts.extend(cls._text_parts(item))
            return parts
        return []
