"""Subprocess shutdown and stderr capture helpers for ACP attempts."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic_ns
from typing import Any

from acp_eval.storage import append_jsonl, append_raw


class ProcessRecorder:
    """Append timestamped process lifecycle events to a JSONL file."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, event: str, **data: Any) -> None:
        append_jsonl(
            self.path,
            {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "monotonic_ns": monotonic_ns(),
                **data,
            },
        )


async def _wait_for_exit(
    process: asyncio.subprocess.Process, timeout: float
) -> int | None:
    try:
        return await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


async def stop_process(
    process: asyncio.subprocess.Process,
    recorder: ProcessRecorder,
    natural_exit_seconds: float = 2.0,
    term_seconds: float = 10.0,
) -> int | None:
    """Close stdin and escalate from natural exit through TERM to KILL."""

    if process.stdin is not None:
        process.stdin.close()

    exit_code = await _wait_for_exit(process, natural_exit_seconds)
    if exit_code is None:
        try:
            process.terminate()
        except ProcessLookupError:
            recorder.write(
                "signal.not_sent",
                signal="SIGTERM",
                initiator="capture",
                reason="natural-exit-timeout",
                process_already_exited=True,
            )
            exit_code = await _wait_for_exit(process, term_seconds)
        else:
            recorder.write(
                "signal.sent",
                signal="SIGTERM",
                initiator="capture",
                reason="natural-exit-timeout",
            )
            exit_code = await _wait_for_exit(process, term_seconds)

    if exit_code is None:
        try:
            process.kill()
        except ProcessLookupError:
            recorder.write(
                "signal.not_sent",
                signal="SIGKILL",
                initiator="capture",
                reason="term-timeout",
                process_already_exited=True,
            )
            exit_code = await process.wait()
        else:
            recorder.write(
                "signal.sent",
                signal="SIGKILL",
                initiator="capture",
                reason="term-timeout",
            )
            exit_code = await process.wait()

    await asyncio.sleep(0)
    recorder.write("process.exited", returncode=exit_code)
    return exit_code


async def drain_stream(
    stream: asyncio.StreamReader,
    destination: Path,
    recorder: ProcessRecorder,
    stream_name: str,
) -> None:
    """Copy a stream to disk and record its EOF or read failure."""

    try:
        while chunk := await stream.read(64 * 1024):
            append_raw(destination, chunk)
    except asyncio.CancelledError:
        recorder.write("stream.error", stream=stream_name, cancelled=True)
        raise
    except Exception as error:
        recorder.write("stream.error", stream=stream_name, error=str(error))
        raise
    recorder.write("stream.eof", stream=stream_name)
