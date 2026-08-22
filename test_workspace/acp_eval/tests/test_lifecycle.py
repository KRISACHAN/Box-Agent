import asyncio
import json
import signal
import sys
from pathlib import Path

import pytest

from acp_eval.lifecycle import ProcessRecorder, drain_stream, stop_process


def read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def start_process(script: str) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


def test_process_recorder_writes_jsonl_with_utc_and_monotonic_timestamps(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "events" / "process.jsonl"

    ProcessRecorder(events_path).write("process.started", pid=123)

    [event] = read_events(events_path)
    assert event["event"] == "process.started"
    assert event["pid"] == 123
    assert str(event["timestamp"]).endswith("+00:00")
    assert isinstance(event["monotonic_ns"], int)


@pytest.mark.asyncio
async def test_stop_process_closes_stdin_and_records_natural_exit_after_stderr_eof(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "process.jsonl"
    stderr_path = tmp_path / "stderr.raw"
    recorder = ProcessRecorder(events_path)
    process = await start_process(
        "import sys; sys.stderr.write('final stderr\\n'); sys.stderr.flush(); sys.stdin.read()"
    )
    assert process.stderr is not None
    drain_task = asyncio.create_task(
        drain_stream(process.stderr, stderr_path, recorder, "stderr")
    )

    exit_code = await stop_process(process, recorder, natural_exit_seconds=1.0)
    await drain_task

    assert exit_code == 0
    assert stderr_path.read_bytes() == b"final stderr\n"
    events = read_events(events_path)
    names = [event["event"] for event in events]
    assert "signal.sent" not in names
    assert names.index("stream.eof") < names.index("process.exited")
    assert events[names.index("stream.eof")]["stream"] == "stderr"


@pytest.mark.asyncio
async def test_stop_process_escalates_from_sigterm_to_sigkill_for_term_ignoring_process(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "process.jsonl"
    recorder = ProcessRecorder(events_path)
    process = await start_process(
        "import signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "sys.stderr.write('ready\\n'); sys.stderr.flush(); time.sleep(60)"
    )
    assert process.stderr is not None
    assert await asyncio.wait_for(process.stderr.readline(), timeout=1.0) == b"ready\n"

    exit_code = await stop_process(
        process,
        recorder,
        natural_exit_seconds=0.05,
        term_seconds=0.05,
    )

    assert exit_code == -signal.SIGKILL
    events = read_events(events_path)
    names = [event["event"] for event in events]
    assert names == ["signal.sent", "signal.sent", "process.exited"]
    assert [event["signal"] for event in events[:2]] == ["SIGTERM", "SIGKILL"]
    assert all(event["initiator"] == "capture" for event in events[:2])
    assert events[0]["reason"] == "natural-exit-timeout"
    assert events[1]["reason"] == "term-timeout"


@pytest.mark.asyncio
async def test_drain_stream_persists_stderr_emitted_immediately_before_exit(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "process.jsonl"
    stderr_path = tmp_path / "stderr.raw"
    recorder = ProcessRecorder(events_path)
    process = await start_process(
        "import sys; sys.stderr.buffer.write(b'last bytes\\x00\\xff'); sys.stderr.flush()"
    )
    assert process.stderr is not None

    await drain_stream(process.stderr, stderr_path, recorder, "stderr")
    await process.wait()

    assert stderr_path.read_bytes() == b"last bytes\x00\xff"
    events = read_events(events_path)
    assert [event["event"] for event in events] == ["stream.eof"]
    assert events[0]["stream"] == "stderr"


@pytest.mark.asyncio
async def test_drain_stream_records_one_error_event_when_cancelled(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "process.jsonl"
    stream = asyncio.StreamReader()
    task = asyncio.create_task(
        drain_stream(stream, tmp_path / "stderr.raw", ProcessRecorder(events_path), "stderr")
    )
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    events = read_events(events_path) if events_path.exists() else []
    assert [event["event"] for event in events] == ["stream.error"]
    assert events[0]["stream"] == "stderr"
    assert events[0]["cancelled"] is True


class ProcessThatPublishesExitAfterTerminateRace:
    def __init__(self) -> None:
        self.stdin = None
        self.returncode: int | None = None
        self.wait_calls = 0

    async def wait(self) -> int:
        self.wait_calls += 1
        if self.wait_calls == 1:
            await asyncio.Event().wait()
        self.returncode = 23
        return self.returncode

    def terminate(self) -> None:
        raise ProcessLookupError

    def kill(self) -> None:
        raise AssertionError("an already-exited process must not be escalated")


@pytest.mark.asyncio
async def test_stop_process_waits_for_exit_after_terminate_race_and_records_not_sent(
    tmp_path: Path,
) -> None:
    events_path = tmp_path / "process.jsonl"
    recorder = ProcessRecorder(events_path)
    process = ProcessThatPublishesExitAfterTerminateRace()

    exit_code = await stop_process(process, recorder, natural_exit_seconds=0.01)

    assert exit_code == 23
    assert process.wait_calls == 2
    events = read_events(events_path)
    assert [event["event"] for event in events] == ["signal.not_sent", "process.exited"]
    assert events[0]["signal"] == "SIGTERM"
    assert events[0]["initiator"] == "capture"
    assert events[0]["reason"] == "natural-exit-timeout"
    assert events[0]["process_already_exited"] is True
    assert events[-1]["returncode"] == 23
