"""Tests for memory tools."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from box_agent.memory import MemoryManager
from box_agent.tools.memory_tool import MemorySearchTool, MemoryWriteTool


@pytest.fixture
def mgr(tmp_path: Path) -> MemoryManager:
    return MemoryManager(memory_dir=str(tmp_path / "memory"))


async def test_memory_write_context_uses_llm_merge_when_available(mgr: MemoryManager):
    mgr.write_context("- Q2 goal: dashboard")
    llm = MagicMock()
    response = MagicMock()
    response.content = (
        '{"operations": ['
        '{"action": "replace", "old": "- Q2 goal: dashboard", "new": "- Q2 goal: launch dashboard by 6/30", "reason": "specific deadline"}'
        ']}'
    )
    llm.generate = AsyncMock(return_value=response)
    tool = MemoryWriteTool(mgr, llm=llm)

    result = await tool.execute("- Q2 goal is launching dashboard by 6/30", category="context")

    assert result.success is True
    assert "context, applied" in result.content
    assert "launch dashboard by 6/30" in mgr.read_context()
    assert llm.generate.await_count == 1


async def test_memory_write_context_without_llm_uses_append_dedup(mgr: MemoryManager):
    mgr.write_context("- Q2 goal: dashboard")
    tool = MemoryWriteTool(mgr)

    result = await tool.execute("- q2 goal: dashboard\n- team lead: Bob", category="context")

    assert result.success is True
    assert "context, append_dedup" in result.content
    context = mgr.read_context()
    assert context.lower().count("q2 goal: dashboard") == 1
    assert "team lead: Bob" in context


async def test_memory_write_waits_off_loop_for_maintenance_transaction(
    mgr: MemoryManager,
):
    transaction_acquired = threading.Event()
    release_transaction = threading.Event()

    def hold_maintenance_transaction():
        with mgr.context_transaction():
            transaction_acquired.set()
            assert release_transaction.wait(timeout=2.0)

    holder = asyncio.create_task(
        asyncio.to_thread(hold_maintenance_transaction)
    )
    assert await asyncio.to_thread(transaction_acquired.wait, 2.0)

    write_task = asyncio.create_task(
        MemoryWriteTool(mgr).execute(
            "- first-turn concurrent memory",
            category="context",
        )
    )
    await asyncio.sleep(0)

    loop_responsive = asyncio.Event()
    asyncio.get_running_loop().call_soon(loop_responsive.set)
    await asyncio.wait_for(loop_responsive.wait(), timeout=0.1)
    assert not write_task.done()

    release_transaction.set()
    result = await asyncio.wait_for(write_task, timeout=2.0)
    await asyncio.wait_for(holder, timeout=2.0)

    assert result.success is True
    assert "- first-turn concurrent memory" in mgr.read_context()


async def test_memory_search_returns_structured_matches_for_host_ui(mgr: MemoryManager):
    mgr.write_context("- Weekly report format: progress/issues/next week\n- Q2 goal: dashboard")
    tool = MemorySearchTool(mgr)

    result = await tool.execute("weekly")

    assert result.success is True
    assert result.raw_output == {
        "type": "memory_search",
        "query": "weekly",
        "matched_memories": [
            {
                "id": "context:1",
                "source": "context",
                "category": "context",
                "text": "- Weekly report format: progress/issues/next week",
            }
        ],
    }


async def test_memory_search_returns_empty_structured_payload(mgr: MemoryManager):
    mgr.write_context("- Q2 goal: dashboard")
    tool = MemorySearchTool(mgr)

    result = await tool.execute("weekly")

    assert result.success is True
    assert result.raw_output == {
        "type": "memory_search",
        "query": "weekly",
        "matched_memories": [],
    }


async def test_memory_search_accepts_explicit_topic(mgr: MemoryManager):
    mgr.append_context("- PPT style: dark editorial", topic="preferences")
    mgr.append_context("- PPT project: Brazil world cup deck", topic="project")
    tool = MemorySearchTool(mgr)

    result = await tool.execute("ppt", topic="project")

    assert result.success is True
    assert result.raw_output == {
        "type": "memory_search",
        "query": "ppt",
        "topic": "project",
        "matched_memories": [
            {
                "id": "context:1",
                "source": "context",
                "category": "context",
                "text": "- PPT project: Brazil world cup deck",
            }
        ],
    }
