from __future__ import annotations

from box_agent.agent_service import AgentService


def test_agent_service_uses_injected_factory_without_protocol_dependencies() -> None:
    captured: dict[str, object] = {}

    class CaptureAgent:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    service = AgentService(agent_factory=CaptureAgent)
    agent = service.create_agent(
        llm_client=object(),
        system_prompt="system",
        tools=[],
        max_steps=2,
        tool_limits=None,
        workspace_dir="workspace",
        token_limit=100,
        session_log=None,
    )

    assert isinstance(agent, CaptureAgent)
    assert captured["system_prompt"] == "system"
    assert captured["session_log"] is None
