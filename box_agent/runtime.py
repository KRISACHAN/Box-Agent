"""Stable execution and composition boundary for framework consumers.

Application adapters should normally use :class:`box_agent.agent.Agent`.
Framework capabilities that need an isolated message/tool set (for example a
sub-agent) may use ``run_agent_loop`` from this module.  Keeping the import
here prevents integrations from depending on the implementation module
``box_agent.core`` directly. Optional workflow policies are selected here so
the kernel depends only on their stable contract, not concrete workflows.
"""

from collections.abc import AsyncIterator
from functools import wraps
from typing import Any

from .core import (
    _negotiate_tool_permission_chain,
    run_agent_loop as _run_agent_loop,
)
from .events import AgentEvent
from .loop_guards import CompletionGate
from .tools.base import Tool, ToolResult
from .tools.model_tool_context import scoped_model_tool_context
from .workflows import create_workflow_policy


@wraps(_run_agent_loop)
def run_agent_loop(**kwargs: Any) -> AsyncIterator[AgentEvent]:
    """Run the kernel with shared workflow and model-tool context composed in."""
    if kwargs.get("workflow_policy") is None:
        completion_gate = kwargs.get("completion_gate")
        kwargs["workflow_policy"] = create_workflow_policy(
            workflow_kind=(
                completion_gate.workflow_checkpoint_kind
                if completion_gate is not None
                else None
            ),
            workspace_dir=kwargs.get("workspace_dir"),
            artifact_root_dir=kwargs.get("artifact_root_dir"),
            workflow_options=(
                completion_gate.workflow_options
                if completion_gate is not None
                else None
            ),
            available_tool_names=frozenset(kwargs.get("tools", {})),
        )
    llm = kwargs.get("llm")
    events = _run_agent_loop(**kwargs)
    return scoped_model_tool_context(
        events,
        model=getattr(llm, "model", ""),
        max_output_tokens=getattr(llm, "max_output_tokens", 0),
    )


async def invoke_tool_with_permissions(
    tool: Tool,
    arguments: dict[str, Any],
    *,
    permission_negotiator: Any | None = None,
) -> tuple[ToolResult, dict[str, Any] | None]:
    """Invoke one Tool through the shared validation and permission policy.

    Adapters sometimes need a deterministic Tool call outside the agent loop,
    for example to inspect a host-supplied attachment before the next model
    turn.  Keep those calls on the same schema-validation, approval, retry, and
    repeated-request boundaries as ordinary model-selected tools.
    """

    try:
        result = await tool.invoke(arguments)
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc!s}"
        return (
            ToolResult(
                success=False,
                error=f"Tool execution failed: {detail}",
                raw_output={
                    "type": "tool_error",
                    "code": "TOOL_EXECUTION_FAILED",
                    "tool": tool.name,
                },
            ),
            None,
        )

    if (
        result.success
        or not result.permission_request
        or permission_negotiator is None
    ):
        return result, None

    return await _negotiate_tool_permission_chain(
        result=result,
        permission_negotiator=permission_negotiator,
        tool_name=tool.name,
        tool=tool,
        arguments=arguments,
        retry_offer_error=lambda: None,
    )


__all__ = [
    "CompletionGate",
    "invoke_tool_with_permissions",
    "run_agent_loop",
]
