from __future__ import annotations

import asyncio

import pytest

from box_agent.tools.browser_runtime_scope import BrowserRuntimeCoordinator


@pytest.mark.asyncio
async def test_browser_runtime_serializes_distinct_turns_but_reenters_same_turn():
    await BrowserRuntimeCoordinator.acquire("session-a:turn-1")

    # Parallel browser calls from one turn share the lease instead of
    # deadlocking behind themselves.
    await asyncio.wait_for(
        BrowserRuntimeCoordinator.acquire("session-a:turn-1"), timeout=0.1
    )

    waiting = asyncio.create_task(
        BrowserRuntimeCoordinator.acquire("session-b:turn-1")
    )
    await asyncio.sleep(0)
    assert waiting.done() is False

    await BrowserRuntimeCoordinator.release("session-a:turn-1")
    await asyncio.wait_for(waiting, timeout=0.5)
    await BrowserRuntimeCoordinator.release("session-b:turn-1")
