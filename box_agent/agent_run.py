"""Run-state facade over an independent Agent session or legacy state object."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Config


@dataclass(slots=True)
class AgentRunHandle:
    """A protocol-independent view over one session's mutable run state.

    AgentSession owns the state. This facade also accepts legacy state objects
    so adapters can retain their existing field access and turn signatures.
    """

    _state: Any

    @property
    def state(self) -> Any:
        """Return the owning session or legacy state object being proxied."""

        return self._state

    @property
    def agent(self) -> Any:
        return self._state.agent

    @property
    def config(self) -> Config | None:
        """Return the owning session's config, if wrapping configured state."""

        return getattr(self._state, "config", None)

    def build_run_options(self, **overrides: Any) -> Any:
        """Build session options, retaining the Agent fallback for legacy state."""

        build_options = getattr(self._state, "build_run_options", None)
        if callable(build_options):
            return build_options(**overrides)
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
