"""Host-neutral run-state facade used during the adapter migration.

``AgentRunHandle`` is intentionally a small compatibility layer for the first
Run Handle migration slice.  ACP still owns its existing ``SessionState``
object and fields, while this facade exposes the state that is shared by a
future CLI/ACP/SDK run service through one stable surface.  Properties proxy
the original object rather than copying values, so existing adapter code and
new callers observe the same cancellation, queue, goal, and Skill state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any


@dataclass(slots=True)
class AgentRunHandle:
    """A protocol-independent view over one session's mutable run state.

    The wrapped state remains the compatibility owner for now.  Keeping the
    proxy deliberately boring lets adapters migrate field-by-field without
    changing their public state shape or turn method signatures.
    """

    _state: Any

    @property
    def state(self) -> Any:
        """Return the compatibility state object being proxied."""

        return self._state

    @property
    def agent(self) -> Any:
        return self._state.agent

    def build_run_options(self, **overrides: Any) -> Any:
        """Snapshot Agent defaults with host-resolved per-turn overrides.

        The adapter still supplies every protocol-specific option.  Keeping
        the dataclass snapshot here gives future adapters one shared entry
        point without changing ``Agent.default_run_options`` or its contract.
        """

        return replace(self.agent.default_run_options(), **overrides)

    @property
    def cancelled(self) -> bool:
        return self._state.cancelled

    @cancelled.setter
    def cancelled(self, value: bool) -> None:
        self._state.cancelled = value

    @property
    def inject_queue(self) -> asyncio.Queue[Any]:
        return self._state.inject_queue

    @property
    def turn_active(self) -> bool:
        return self._state.turn_active

    @turn_active.setter
    def turn_active(self, value: bool) -> None:
        self._state.turn_active = value

    @property
    def current_turn_id(self) -> str:
        return self._state.current_turn_id

    @current_turn_id.setter
    def current_turn_id(self, value: str) -> None:
        self._state.current_turn_id = value

    @property
    def goal(self) -> Any:
        """Expose the Agent-owned goal without duplicating it in the handle."""

        return self._state.agent.goal

    @property
    def explicitly_allowed_skill_names(self) -> set[str]:
        return self._state.explicitly_allowed_skill_names

    @property
    def skill_selector(self) -> Any:
        return self._state.skill_selector

    @property
    def skill_runtime_context(self) -> Any:
        return self._state.skill_runtime_context

    @property
    def preloaded_skill_names(self) -> list[str]:
        return self._state.preloaded_skill_names

    @property
    def preloaded_skill_hashes(self) -> dict[str, str]:
        return self._state.preloaded_skill_hashes

    @property
    def preloaded_skill_attributions(self) -> dict[str, Any]:
        return self._state.preloaded_skill_attributions


__all__ = ["AgentRunHandle"]
