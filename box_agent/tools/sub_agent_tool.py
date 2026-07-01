"""Sub-agent tool for isolated context execution.

Spawns a child agent loop with its own message history so that
intermediate tool output (file reads, exploratory analysis, etc.)
stays out of the parent context.  Only the final summary is returned.

Multiple sub-agent calls are ``parallel_safe`` and will be executed
concurrently via ``asyncio.gather`` in the core loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable
from uuid import uuid4

from ..events import (
    ArtifactEvent,
    DoneEvent,
    ErrorEvent,
    LLMOutputEvent,
    ProgressEvent,
    StepStart,
    SubAgentEvent,
    ToolCallResult,
    ToolCallStart,
    WebSearchEvent,
)
from ..schema import Message
from .base import EventEmittingTool, Tool, ToolResult

_SUB_AGENT_SYSTEM_PROMPT = """\
You are a focused sub-agent executing a specific task delegated by the main agent.

Rules:
1. You inherit the parent agent's system instructions and must follow them unless the \
delegated task gives a narrower, non-conflicting scope.
2. Complete only the assigned isolated work unit. Respect any path, file, prefix, \
or output constraints in the delegated task.
3. Do not overwrite shared files or final deliverables unless the delegated task \
explicitly assigns that exact output to you.
4. If a Jupyter kernel session already exists, variables from previous executions \
are still in scope — reuse them directly.
5. When you are done, output a concise but complete summary of your findings or \
results.  Include key numbers, conclusions, and any file paths produced.
6. Do NOT ask follow-up questions — complete the task with what you have.
"""


class SubAgentTool(EventEmittingTool):
    """Run a task in an isolated agent context.

    The child agent shares the same LLM client and tool instances (so
    Jupyter kernel sessions, sandbox state, etc. are preserved), but has
    its own message history.  Only the final textual summary is returned
    to the parent agent, keeping the parent context clean.
    """

    parallel_safe = True

    def __init__(
        self,
        *,
        llm,
        parent_tools: dict[str, Tool],
        workspace_dir: str | None = None,
        max_steps: int = 40,
        token_limit: int = 40_000,
        parent_system_prompt: str | None = None,
        no_progress_limit: int = 6,
        artifact_detection_enabled: bool = True,
        artifact_root_dir: str | None = None,
    ):
        super().__init__()
        self._llm = llm
        # Snapshot taken at construction time. Used as a fallback only; the
        # live parent tool map is preferred (see ``set_tool_provider``) so that
        # tools that load *after* construction — notably MCP tools such as
        # ``web_search`` which arrive asynchronously — are still inherited by
        # child agents. Exclude ourselves to prevent recursive spawning.
        self._child_tools_snapshot = {
            n: t for n, t in parent_tools.items() if n != self.name
        }
        # Callable returning the parent agent's *live* tool map. Wired by
        # ``Agent.__init__`` after the agent's ``self.tools`` dict (which
        # ``register_mcp_tools`` mutates in place) is built.
        self._tool_provider: Callable[[], dict[str, Tool]] | None = None
        self._workspace_dir = workspace_dir
        self._max_steps = max_steps
        self._token_limit = token_limit
        self._parent_system_prompt = parent_system_prompt
        self._no_progress_limit = no_progress_limit
        self._artifact_detection_enabled = artifact_detection_enabled
        self._artifact_root_dir = artifact_root_dir

    def set_parent_system_prompt(self, system_prompt: str) -> None:
        """Attach the finalized parent prompt so child agents inherit constraints."""
        self._parent_system_prompt = system_prompt

    def set_tool_provider(self, provider: Callable[[], dict[str, Tool]]) -> None:
        """Wire a callable returning the parent agent's live tool map.

        The provider is invoked at ``execute`` time so child agents inherit the
        parent's current toolset — including MCP tools (e.g. ``web_search``)
        registered after this tool was constructed. Without this, the child
        would be frozen with the construction-time snapshot and silently lose
        late-loading tools, forcing it into brittle fallbacks (raw ``curl``).
        """
        self._tool_provider = provider

    def _resolve_child_tools(self) -> dict[str, Tool]:
        """Return the child toolset: live parent map minus ``sub_agent``."""
        if self._tool_provider is not None:
            try:
                live = self._tool_provider()
            except Exception:
                live = None
            if live:
                return {n: t for n, t in live.items() if n != self.name}
        return dict(self._child_tools_snapshot)

    @property
    def name(self) -> str:
        return "sub_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate one isolated, self-contained work unit to a sub-agent. "
            "Use sub_agent when the work can run independently and the parent only needs a concise "
            "summary, evidence, findings, or paths to draft artifacts. Use it for separable units "
            "that need independent evidence gathering, fact checking, analysis, comparison, drafting, "
            "or review. Good examples include reading many files to answer one question, deep codebase "
            "search, research over independent candidates or source ranges, exploratory data analysis, "
            "reviewing one slice of outputs, processing one input file, or drafting one independent "
            "page/section/file.\n\n"
            "Mandatory trigger: when a task needs evidence gathering, fact checking, analysis, drafting, "
            "or review across more than 5 structurally similar units that can be isolated, launch 3-7 "
            "sub_agent calls first unless the user "
            "explicitly says not to parallelize or the units cannot be safely isolated. Each call "
            "must be scoped to a single small unit such as 1 file, 1 page, 1 data slice, 1 candidate, "
            "1 source range, 1 time range, 1 evaluation dimension, or 1 sub-question. Each sub-agent "
            "may create draft files or artifacts only in an explicitly assigned unique path, directory, "
            "or filename prefix. If the final deliverable is a single file, still split independent "
            "units into draft fragments, local partial files, or local evidence/finding summaries and "
            "let the parent merge them into the single final answer or file. Do not assign two "
            "sub-agents to write the same file or shared output.\n\n"
            "The parent agent must own coordination: choose the split, merge results, resolve conflicts, "
            "write final deliverables, package/release outputs, update shared files, and run final "
            "validation. The sub-agent must report changed/created paths, findings, assumptions, and "
            "remaining risks.\n\n"
            "When launching parallel sub-agents, give each call a short, distinct `title` naming only "
            "what differs between siblings (the page/file/slice), not the shared context — this is what "
            "the user sees as the per-task label."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": (
                        "A short, distinct label (about 4-12 characters / 2-6 words) "
                        "naming what makes THIS unit different from its siblings — e.g. "
                        "the page topic, file name, or data slice. Do NOT repeat the "
                        "shared context that every sibling shares (the company name, "
                        "the common task stem); put only the distinguishing part here. "
                        "Used as the display label in parallel-task UIs."
                    ),
                },
                "task": {
                    "type": "string",
                    "description": (
                        "A clear, self-contained description of the task for the "
                        "sub-agent to execute. Include all necessary context — the "
                        "sub-agent cannot see prior conversation history."
                    ),
                },
            },
            "required": ["task"],
        }

    # Event types worth surfacing to the parent.
    _FORWARD_TYPES = (
        StepStart,
        ProgressEvent,
        LLMOutputEvent,
        ToolCallStart,
        ToolCallResult,
        WebSearchEvent,
        ArtifactEvent,
        ErrorEvent,
    )

    async def execute_with_event_context(
        self,
        *,
        event_queue: asyncio.Queue,
        parent_tool_call_id: str,
        **kwargs: Any,
    ) -> ToolResult:
        return await self.execute(
            **kwargs,
            _event_queue=event_queue,
            _parent_tool_call_id=parent_tool_call_id,
        )

    async def execute(  # type: ignore[override]
        self,
        task: str,
        title: str | None = None,
        *,
        _event_queue: asyncio.Queue | None = None,
        _parent_tool_call_id: str | None = None,
    ) -> ToolResult:
        # Import here to avoid circular dependency (core → tools → core).
        from ..core import run_agent_loop

        system_prompt = _SUB_AGENT_SYSTEM_PROMPT
        if self._parent_system_prompt:
            system_prompt = (
                f"{system_prompt.rstrip()}\n\n"
                "## Inherited parent system prompt\n"
                "The following instructions are inherited from the parent agent. "
                "They define global behavior, safety, workspace, skill, output, and "
                "task-specific constraints that also apply inside this sub-agent.\n\n"
                f"{self._parent_system_prompt}"
            )

        messages: list[Message] = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=task),
        ]

        # Resolve the child toolset from the parent's *live* tool map so
        # late-loaded tools (e.g. MCP web_search) are inherited.
        child_tools = self._resolve_child_tools()

        queue = _event_queue if _event_queue is not None else self._event_queue
        parent_tool_call_id = (
            _parent_tool_call_id
            if _parent_tool_call_id is not None
            else self._parent_tool_call_id
        )
        # Single-line preview: collapse whitespace, truncate
        task_preview = " ".join(task.split())[:50]
        # Short, distinct label provided by the parent model. Falls back to the
        # task preview when omitted so older callers / hosts still get a label.
        sub_title = " ".join((title or "").split())[:60] or task_preview
        sub_agent_id = f"subagent-{uuid4().hex}"

        final_content = ""
        # Track child tool_call_ids that we forwarded a Start for but have
        # not yet seen a matching Result for. If the child loop raises mid-
        # flight, we synthesize a stub Result event for each so the host
        # UI doesn't show perpetually-running tool tiles and any consumer
        # building model history sees a balanced start/result pair.
        pending_child_tc: dict[str, str] = {}  # tc_id → tool_name
        try:
            async for event in run_agent_loop(
                llm=self._llm,
                messages=messages,
                tools=child_tools,
                max_steps=self._max_steps,
                token_limit=self._token_limit,
                workspace_dir=self._workspace_dir,
                no_progress_limit=self._no_progress_limit,
                artifact_detection_enabled=self._artifact_detection_enabled,
                artifact_root_dir=self._artifact_root_dir,
            ):
                if isinstance(event, ToolCallStart):
                    pending_child_tc[event.tool_call_id] = event.tool_name
                elif isinstance(event, ToolCallResult):
                    pending_child_tc.pop(event.tool_call_id, None)

                if isinstance(event, DoneEvent):
                    final_content = event.final_content
                elif queue is not None and isinstance(event, self._FORWARD_TYPES):
                    queue.put_nowait(
                        SubAgentEvent(
                            parent_tool_call_id=parent_tool_call_id,
                            task_preview=task_preview,
                            event=event,
                            sub_agent_id=sub_agent_id,
                            title=sub_title,
                        )
                    )
        except Exception as exc:
            if queue is not None and pending_child_tc:
                for tc_id, tool_name in pending_child_tc.items():
                    queue.put_nowait(
                        SubAgentEvent(
                            parent_tool_call_id=parent_tool_call_id,
                            task_preview=task_preview,
                            event=ToolCallResult(
                                tool_call_id=tc_id,
                                tool_name=tool_name,
                                success=False,
                                content="",
                                error=(
                                    f"Sub-agent interrupted before tool completed: "
                                    f"{type(exc).__name__}: {exc}"
                                ),
                            ),
                            sub_agent_id=sub_agent_id,
                            title=sub_title,
                        )
                    )
            return ToolResult(
                success=False,
                content="",
                error=f"Sub-agent execution failed: {type(exc).__name__}: {exc}",
            )

        if not final_content:
            return ToolResult(
                success=False,
                content="",
                error="Sub-agent finished without producing output.",
            )

        return ToolResult(success=True, content=final_content)
