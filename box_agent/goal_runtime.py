"""Pure Goal autopilot decisions shared by host adapters.

The CLI and ACP still own their turn loops, logging, rendering, and host
metadata.  These helpers only calculate the two pieces of generic policy that
must stay identical between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def goal_autopilot_budget_exhausted(
    *,
    continuations: int,
    started_at: float,
    now: float,
    max_turns: int,
    max_seconds: float,
) -> bool:
    """Return whether the continuation count or elapsed-time budget is spent."""

    return continuations >= max_turns or now - started_at >= max_seconds


def record_goal_autopilot_progress(
    *,
    before_signature: Any,
    after_signature: Any,
    no_progress_turns: int,
    no_progress_limit: int,
) -> tuple[int, bool]:
    """Update stall count and report whether the configured limit was reached."""

    next_no_progress_turns = (
        no_progress_turns + 1
        if after_signature == before_signature
        else 0
    )
    exhausted = (
        no_progress_limit > 0
        and next_no_progress_turns >= no_progress_limit
    )
    return next_no_progress_turns, exhausted


@dataclass(slots=True)
class GoalAutopilotController:
    """Track shared continuation budgets while adapters own turn execution.

    ACP and CLI still decide when to invoke the Agent and how to report a
    continuation.  This controller keeps the mutable counters and the two
    generic stop conditions in one place, avoiding drift in their loops.
    """

    started_at: float
    max_turns: int
    max_seconds: float
    no_progress_limit: int
    continuations: int = 0
    budget_exhausted: bool = False
    no_progress_turns: int = 0
    no_progress_exhausted: bool = False

    def budget_exhausted_at(self, now: float) -> bool:
        exhausted = goal_autopilot_budget_exhausted(
            continuations=self.continuations,
            started_at=self.started_at,
            now=now,
            max_turns=self.max_turns,
            max_seconds=self.max_seconds,
        )
        if exhausted:
            self.budget_exhausted = True
        return exhausted

    def begin_continuation(self) -> int:
        """Advance the continuation count after the budget gate succeeds."""

        self.continuations += 1
        return self.continuations

    def record_progress(self, before_signature: Any, after_signature: Any) -> bool:
        self.no_progress_turns, self.no_progress_exhausted = (
            record_goal_autopilot_progress(
                before_signature=before_signature,
                after_signature=after_signature,
                no_progress_turns=self.no_progress_turns,
                no_progress_limit=self.no_progress_limit,
            )
        )
        return self.no_progress_exhausted


__all__ = [
    "GoalAutopilotController",
    "goal_autopilot_budget_exhausted",
    "record_goal_autopilot_progress",
]
