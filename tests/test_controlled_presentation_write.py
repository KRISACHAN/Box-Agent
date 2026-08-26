import json

import pytest

from box_agent.tools.file_tools import WriteTool
from box_agent.workflows.controlled_presentation import ControlledPresentationPolicy
from box_agent.workflows.presentation_checkpoint import (
    CONTROLLED_PRESENTATION_CHECKPOINT_MARKER,
)


@pytest.mark.asyncio
async def test_controlled_patch_chunk_transaction_survives_filesystem_checkpoint(
    tmp_path,
):
    """A pending atomic patch write must not look like a missing patch."""
    output = tmp_path / "output"
    output.mkdir()
    (output / "outline.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "page": 1,
                        "title": "Exact title",
                        "message": "Exact message",
                        "bullets": ["Exact bullet"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    qa = output / "qa"
    qa.mkdir()
    (qa / "outline_check.json").write_text('{"ok": true}', encoding="utf-8")
    (output / "deck.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "id": "slide-01",
                        "layout_id": "cover-hero-v1",
                        "source_outline_page": 1,
                        "props": {"title": "输入演示标题"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    policy = ControlledPresentationPolicy(
        workspace_dir=str(tmp_path),
        artifact_root_dir=None,
    )
    initial = policy.build_checkpoint()
    assert initial is not None
    policy.update_checkpoint(initial)
    assert policy.stage == "content_patch"

    tool = WriteTool(
        workspace_dir=str(tmp_path),
        relative_root_dir=str(output),
    )
    first_arguments = {
        "path": "deck.patch.json",
        "content": '{"slides":',
        "chunk_index": 0,
        "final": False,
    }
    accepted = await tool.execute(**first_arguments)
    assert accepted.success is True
    assert not (output / "deck.patch.json").exists()
    policy.record_tool_result("write_file", first_arguments, accepted)

    pending = policy.build_checkpoint()

    assert pending is not None
    assert f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}content_patch" in pending
    assert "patch=write_pending" in pending
    assert 'WRITE_PENDING={"path":"deck.patch.json","next_chunk_index":1' in pending
    assert "Do not restart at chunk_index=0" in pending
    policy.update_checkpoint(pending)
    blocked_restart = policy.tool_call_error(
        "write_file",
        {
            "path": "deck.patch.json",
            "content": '{"slides":{"slide-01":{}}}',
            "chunk_index": 0,
            "final": True,
        },
        verified_evidence_urls=set(),
    )
    assert blocked_restart is not None
    assert "CONTROLLED_PRESENTATION_WRITE_TRANSACTION_PENDING" in blocked_restart
    assert (
        policy.tool_call_error(
            "write_file",
            {
                "path": "deck.patch.json",
                "content": "{}}",
                "chunk_index": 1,
                "final": True,
            },
            verified_evidence_urls=set(),
        )
        is None
    )

    final_arguments = {
        "path": "deck.patch.json",
        "content": "{}}",
        "chunk_index": 1,
        "final": True,
    }
    committed = await tool.execute(**final_arguments)
    assert committed.success is True
    policy.record_tool_result("write_file", final_arguments, committed)
    complete = policy.build_checkpoint()
    assert complete is not None
    assert f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}apply_patch" in complete
    assert "WRITE_PENDING=" not in complete


@pytest.mark.asyncio
async def test_controlled_complete_outline_chunk_can_finalize_with_empty_chunk(tmp_path):
    """A complete JSON body sent with final=false remains a live transaction."""
    output = tmp_path / "output"
    output.mkdir()
    policy = ControlledPresentationPolicy(
        workspace_dir=str(tmp_path),
        artifact_root_dir=None,
    )
    initial = policy.build_checkpoint()
    assert initial is not None
    policy.update_checkpoint(initial)
    assert policy.stage == "outline"

    tool = WriteTool(
        workspace_dir=str(tmp_path),
        relative_root_dir=str(output),
    )
    outline_body = json.dumps(
        {
            "deck_goal": "Explain the plan",
            "audience": "Decision makers",
            "source_mode": "user_provided",
            "storyline": "One clear page",
            "slides": [
                {
                    "page": 1,
                    "title": "Exact title",
                    "message": "Exact message",
                    "bullets": ["Exact bullet one", "Exact bullet two"],
                    "layout": "cover",
                    "visual": "hero",
                    "evidence": [],
                }
            ],
        }
    )
    first_arguments = {
        "path": "outline.json",
        "content": outline_body,
        "chunk_index": 0,
        "final": False,
    }
    accepted = await tool.execute(**first_arguments)
    assert accepted.success is True
    policy.record_tool_result("write_file", first_arguments, accepted)

    pending = policy.build_checkpoint()

    assert pending is not None
    assert f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}outline" in pending
    assert "outline=write_pending" in pending
    assert 'WRITE_PENDING={"path":"outline.json","next_chunk_index":1' in pending
    assert 'send content="" with final=true' in pending
    policy.update_checkpoint(pending)
    final_arguments = {
        "path": "outline.json",
        "content": "",
        "chunk_index": 1,
        "final": True,
    }
    assert (
        policy.tool_call_error(
            "write_file",
            final_arguments,
            verified_evidence_urls=set(),
        )
        is None
    )
    committed = await tool.execute(**final_arguments)
    assert committed.success is True
    policy.record_tool_result("write_file", final_arguments, committed)

    complete = policy.build_checkpoint()

    assert complete is not None
    assert f"{CONTROLLED_PRESENTATION_CHECKPOINT_MARKER}outline_qa" in complete
    assert "WRITE_PENDING=" not in complete
