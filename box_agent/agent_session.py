"""Protocol-independent Agent session state and configuration boundary."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .agent import Agent, AgentRunOptions
from .agent_run import AgentRunHandle
from .agent_runtime import AgentFactory
from .agent_service import AgentService
from .config import Config
from .events import AgentEvent, DoneEvent, StopReason
from .execution_profile import ExecutionProfile

if TYPE_CHECKING:
    from .env_context import EnvContext
    from .llm import SessionBoundLLM
    from .session_log import SessionLog
    from .tools.permissions import GrantStore, PermissionEngine
    from .tools.runtime import SkillRuntimeContext
    from .tools.skill_preload import SkillPreloadAttribution
    from .tools.skill_scratch import SkillScratchDirectory


@dataclass
class AgentSession:
    """Own live Agent state without depending on a host protocol.

    ``create`` requires the existing Config explicitly. Keep its reference and
    the existing read timing: constructor settings are resolved once, while
    turn-level policy reads use this session's config. ``None`` is supported
    only for compatibility with callers wrapping an already-created Agent.
    Config is not included in repr; durable facts still belong to SessionLog.
    """

    agent: Agent
    config: Config | None = field(
        default=None, kw_only=True, repr=False, compare=False,
    )
    session_llm: SessionBoundLLM | None = None
    summary_llm: SessionBoundLLM | None = None
    cancelled: bool = False
    output_dir: str | None = None
    skill_scratch_dir: SkillScratchDirectory | None = None
    artifact_mode: str = "output"
    permission_engine: PermissionEngine | None = None
    grant_store: GrantStore | None = None
    memory_extractor: Any | None = None
    inject_queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    turn_active: bool = False
    memory_block: str | None = None
    thinking_enabled: bool = False
    execution_profile: ExecutionProfile = "standard"
    explicitly_allowed_skill_names: set[str] = field(default_factory=set)
    env_context: EnvContext | None = None
    skill_runtime_context: SkillRuntimeContext | None = None
    skill_loader: Any | None = None
    skill_selector: Any | None = None
    force_plan_start: bool = False
    require_plan_approval: bool = False
    pending_plan_approval: dict[str, Any] | None = None
    preloaded_skill_names: list[str] = field(default_factory=list)
    preloaded_skill_hashes: dict[str, str] = field(default_factory=dict)
    preloaded_skill_attributions: dict[str, SkillPreloadAttribution] = field(
        default_factory=dict,
    )
    waiting_for_user_input: bool = False
    turn_counter: int = 0
    continuation_applied: bool = False
    current_turn_id: str = ""
    source_text: str = ""
    last_error: str | None = None
    last_error_code: int | str | None = None
    last_error_category: str | None = None
    last_error_details: dict[str, Any] | None = None
    mcp_fallback_tools: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._run_handle = AgentRunHandle(self)

    @property
    def run_handle(self) -> AgentRunHandle:
        return self._run_handle

    @classmethod
    def create(
        cls,
        *,
        config: Config,
        llm_client: Any,
        system_prompt: str,
        tools: list[Any],
        workspace_dir: str | Path | None = None,
        token_limit: int | None = None,
        hooks: list[Any] | None = None,
        session_log: SessionLog | None = None,
        utility: bool = False,
        agent_factory: AgentFactory = Agent,
        **state: Any,
    ) -> AgentSession:
        """Resolve session configuration through the existing Agent factory.

        Hosts supply prepared capabilities and resolved workspace/model
        overrides. Protocol-specific metadata belongs to their subclass.
        """

        settings = config.agent
        agent = AgentService(agent_factory=agent_factory).create_agent(
            llm_client=llm_client,
            system_prompt=system_prompt,
            tools=tools,
            hooks=hooks,
            max_steps=settings.max_steps,
            tool_limits=config.tool_limits,
            workspace_dir=str(
                workspace_dir if workspace_dir is not None else settings.workspace_dir
            ),
            token_limit=(
                config.llm.context_token_limit if token_limit is None else token_limit
            ),
            thinking_enabled=state.get("thinking_enabled", False),
            max_parallel_tools=settings.max_parallel_tools,
            parallel_tool_timeout_seconds=settings.parallel_tool_timeout_seconds,
            provider_stale_seconds=settings.provider_stale_seconds,
            memory_promotion_enabled=settings.memory_promotion_proposal_enabled,
            memory_promotion_hit_threshold=settings.memory_promotion_hit_threshold,
            memory_promotion_cooldown_days=settings.memory_promotion_cooldown_days,
            truncation_continuation_enabled=settings.retry_on_suspected_truncation,
            max_truncation_continuations=settings.max_truncation_continuations,
            max_truncated_tool_call_retries=settings.max_truncated_tool_call_retries,
            truncated_tool_call_boost_cap=settings.truncated_tool_call_boost_cap,
            context_resource_dedup_enabled=settings.context_resource_dedup_enabled,
            deferred_mcp_loading_enabled=(
                not utility
                and config.tools.enable_mcp
                and config.tools.mcp.deferred_loading_enabled
            ),
            session_log=session_log,
        )
        return cls(agent=agent, config=config, **state)

    def build_run_options(self, **overrides: Any) -> AgentRunOptions:
        """Bind session state before applying explicit host turn overrides."""

        values = {
            "summary_llm": self.summary_llm,
            "is_cancelled": lambda: self.cancelled,
            "inject_queue": self.inject_queue,
        }
        if self.memory_extractor is not None:
            values["memory_extractor"] = self.memory_extractor
        values.update(overrides)
        return replace(self.agent.default_run_options(), **values)

    def request_cancel(self) -> None:
        """Request cooperative cancellation through this session's options."""

        self.cancelled = True

    async def run_events(
        self,
        *,
        options: AgentRunOptions | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run through the public Agent API and close its stream on exit."""

        enclosing_turn_active = self.turn_active
        self.turn_active = True
        self.agent.last_stop_reason = None
        events = None
        try:
            events = self.agent.run_events(
                options=options if options is not None else self.build_run_options(),
            )
            async for event in events:
                if isinstance(event, DoneEvent):
                    self.agent.last_stop_reason = event.stop_reason.value
                    self.waiting_for_user_input = (
                        event.stop_reason == StopReason.WAITING_FOR_USER
                    )
                yield event
        finally:
            try:
                if events is not None:
                    await events.aclose()
            finally:
                # ACP can own a wider prompt spanning several continuation runs.
                self.turn_active = enclosing_turn_active


__all__ = ["AgentSession"]
