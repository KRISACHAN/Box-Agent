import asyncio

import pytest

import box_agent.core as core
from box_agent.schema import StreamEvent


@pytest.mark.asyncio
async def test_stream_wrapper_emits_activity_while_provider_waits(monkeypatch):
    monkeypatch.setattr(core, "LLM_ACTIVITY_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(core, "LLM_PROVIDER_STALE_SECONDS", 1.0)

    async def slow_stream():
        await asyncio.sleep(0.025)
        yield StreamEvent(type="text", delta="ok")
        yield StreamEvent(type="finish", finish_reason="stop")

    events = [event async for event in core._stream_with_activity(slow_stream())]

    activity = [event for event in events if event.type == "activity"]
    assert activity
    assert activity[0].activity["protocol"] == "agent_activity_v1"
    assert activity[0].activity["phase"] == "provider_wait"
    assert any(event.type == "text" for event in events)


@pytest.mark.asyncio
async def test_stream_wrapper_stops_stale_provider(monkeypatch):
    monkeypatch.setattr(core, "LLM_ACTIVITY_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(core, "LLM_PROVIDER_STALE_SECONDS", 0.025)

    async def stuck_stream():
        await asyncio.sleep(10)
        yield StreamEvent(type="text", delta="late")

    events = [event async for event in core._stream_with_activity(stuck_stream())]

    assert events[-1].type == "finish"
    assert events[-1].finish_reason == "provider_stale"
    assert not any(event.type == "text" for event in events)
