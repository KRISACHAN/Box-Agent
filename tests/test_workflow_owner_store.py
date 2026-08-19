from __future__ import annotations

import json

from box_agent.workflow_owner_store import (
    clear_workflow_owner,
    load_workflow_owner,
    save_workflow_owner,
)


def test_owner_round_trips_outside_workspace(tmp_path) -> None:
    root = tmp_path / "session-state"

    saved = save_workflow_owner(
        session_id="upstream-session",
        workflow_kind="external_skill",
        workflow_options={"skill_name": "third-party", "max": 3},
        root_dir=root,
    )
    loaded = load_workflow_owner(
        session_id="upstream-session",
        root_dir=root,
    )

    assert saved is not None
    assert loaded == saved
    assert (root / "upstream-session" / "workflow-owner.json").is_file()


def test_owner_rejects_corruption_and_session_mismatch(tmp_path) -> None:
    root = tmp_path / "session-state"
    save_workflow_owner(
        session_id="session-a",
        workflow_kind="controlled_presentation",
        workflow_options={"research_mode": "auto"},
        root_dir=root,
    )
    path = root / "session-a" / "workflow-owner.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["workflow_kind"] = "external_skill"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_workflow_owner(session_id="session-a", root_dir=root) is None
    assert load_workflow_owner(session_id="session-b", root_dir=root) is None


def test_owner_rejects_unregistered_workflow_and_can_clear(tmp_path) -> None:
    root = tmp_path / "session-state"

    assert save_workflow_owner(
        session_id="session-a",
        workflow_kind="third_party_python",
        workflow_options={},
        root_dir=root,
    ) is None
    save_workflow_owner(
        session_id="session-a",
        workflow_kind="external_skill",
        workflow_options={},
        root_dir=root,
    )

    assert clear_workflow_owner(session_id="session-a", root_dir=root) is True
    assert load_workflow_owner(session_id="session-a", root_dir=root) is None
