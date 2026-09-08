from __future__ import annotations

from box_agent.goal_runtime import (
    GoalAutopilotController,
    goal_autopilot_budget_exhausted,
    record_goal_autopilot_progress,
)


def test_goal_autopilot_budget_exhausted_when_turn_or_time_limit_reached() -> None:
    assert goal_autopilot_budget_exhausted(
        continuations=2,
        started_at=10.0,
        now=11.0,
        max_turns=2,
        max_seconds=60.0,
    )
    assert goal_autopilot_budget_exhausted(
        continuations=1,
        started_at=10.0,
        now=70.0,
        max_turns=2,
        max_seconds=60.0,
    )
    assert not goal_autopilot_budget_exhausted(
        continuations=1,
        started_at=10.0,
        now=11.0,
        max_turns=2,
        max_seconds=60.0,
    )


def test_record_goal_autopilot_progress_resets_or_increments_stall_count() -> None:
    assert record_goal_autopilot_progress(
        before_signature=("active",),
        after_signature=("active",),
        no_progress_turns=1,
        no_progress_limit=2,
    ) == (2, True)
    assert record_goal_autopilot_progress(
        before_signature=("active",),
        after_signature=("complete",),
        no_progress_turns=1,
        no_progress_limit=2,
    ) == (0, False)


def test_goal_autopilot_controller_tracks_budget_and_progress() -> None:
    controller = GoalAutopilotController(
        started_at=10.0,
        max_turns=2,
        max_seconds=60.0,
        no_progress_limit=2,
    )

    assert controller.begin_continuation() == 1
    assert not controller.budget_exhausted_at(11.0)
    assert not controller.record_progress(("active",), ("active",))
    assert controller.no_progress_turns == 1
    assert controller.record_progress(("active",), ("active",))
    assert controller.no_progress_exhausted is True

    assert controller.begin_continuation() == 2
    assert controller.budget_exhausted_at(11.0)
    assert controller.budget_exhausted is True
