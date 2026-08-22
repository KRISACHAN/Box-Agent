import json
from datetime import datetime, timezone
from pathlib import Path

import acp_eval.protocol as protocol_module
from acp_eval.protocol import ACPAccumulator, ProtocolRecorder


def test_recorder_preserves_malformed_stdout_without_fabricating_protocol_message(
    tmp_path: Path,
) -> None:
    recorder = ProtocolRecorder(
        tmp_path,
        wall_clock=lambda: datetime(2026, 8, 21, tzinfo=timezone.utc),
        monotonic_ns=lambda: 12,
    )
    malformed = b'{"method": broken}\n'

    assert recorder.record_received(malformed) is None

    assert (tmp_path / "acp-stdout.raw").read_bytes() == malformed
    assert not (tmp_path / "protocol.jsonl").exists()
    assert recorder.parse_errors[0].byte_offset == 0
    assert recorder.parse_errors[0].raw_size == len(malformed)
    assert "Expecting value" in recorder.parse_errors[0].error


def test_recorder_persists_received_raw_bytes_before_normalizing_message(
    tmp_path: Path, monkeypatch,
) -> None:
    raw_line = b'{"method":"session/update","params":{"sequence":2}}\n'
    recorder = ProtocolRecorder(
        tmp_path,
        wall_clock=lambda: datetime(2026, 8, 21, 0, 1, tzinfo=timezone.utc),
        monotonic_ns=lambda: 99,
    )
    original_append_jsonl = protocol_module.append_jsonl

    def checked_append_jsonl(path: Path, payload: dict) -> None:
        assert (tmp_path / "acp-stdout.raw").read_bytes() == raw_line
        original_append_jsonl(path, payload)

    monkeypatch.setattr(protocol_module, "append_jsonl", checked_append_jsonl)

    message = recorder.record_received(raw_line)

    assert message == {"method": "session/update", "params": {"sequence": 2}}
    assert [json.loads(line) for line in (tmp_path / "protocol.jsonl").read_text().splitlines()] == [
        {
            "sequence": 1,
            "direction": "received",
            "timestamp": "2026-08-21T00:01:00+00:00",
            "monotonic_ns": 99,
            "message": message,
        }
    ]


def test_recorder_numbers_both_directions_and_accepts_large_frames(tmp_path: Path) -> None:
    wall_times = iter(
        [
            datetime(2026, 8, 21, 0, 1, tzinfo=timezone.utc),
            datetime(2026, 8, 21, 0, 2, tzinfo=timezone.utc),
        ]
    )
    monotonic_times = iter([100, 200])
    recorder = ProtocolRecorder(tmp_path, lambda: next(wall_times), lambda: next(monotonic_times))
    sent = {"id": 1, "method": "session/prompt", "params": {"prompt": []}}
    large_message = {"method": "session/update", "params": {"payload": "x" * (64 * 1024)}}

    sent_bytes = recorder.record_sent(sent)
    received = recorder.record_received(json.dumps(large_message).encode("utf-8") + b"\n")

    assert sent_bytes == b'{"id":1,"method":"session/prompt","params":{"prompt":[]}}\n'
    assert received == large_message
    assert len((tmp_path / "acp-stdout.raw").read_bytes()) > 64 * 1024
    entries = [json.loads(line) for line in (tmp_path / "protocol.jsonl").read_text().splitlines()]
    assert [(entry["sequence"], entry["direction"]) for entry in entries] == [
        (1, "sent"),
        (2, "received"),
    ]
    assert [entry["timestamp"] for entry in entries] == [
        "2026-08-21T00:01:00+00:00",
        "2026-08-21T00:02:00+00:00",
    ]
    assert [entry["monotonic_ns"] for entry in entries] == [100, 200]


def test_accumulator_records_observed_acp_fields_without_success_judgment() -> None:
    accumulator = ACPAccumulator()
    accumulator.consume(
        {
            "method": "session/request_permission",
            "params": {"options": [{"kind": "allow_once"}]},
        }
    )
    accumulator.consume(
        {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "first "},
                }
            },
        }
    )
    accumulator.consume(
        {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "second"},
                    "rawOutput": {
                        "type": "turn_usage",
                        "tokenUsage": {
                            "promptTokens": 12,
                            "completionTokens": 3,
                            "totalTokens": 15,
                            "calls": 1,
                        },
                    },
                }
            },
        }
    )
    final_response = {
        "id": 7,
        "result": {
            "stopReason": "end_turn",
            "_meta": {"usage": {"totalTokens": 15}, "turnId": "turn-1"},
        },
    }
    accumulator.consume(final_response)

    assert accumulator.permission_request_count == 1
    assert accumulator.assistant_text == "first second"
    assert accumulator.token_usage == {
        "promptTokens": 12,
        "completionTokens": 3,
        "totalTokens": 15,
        "calls": 1,
    }
    assert accumulator.final_response == final_response
    assert accumulator.final_response_metadata == {
        "usage": {"totalTokens": 15},
        "turnId": "turn-1",
    }
    assert not hasattr(accumulator, "success")
