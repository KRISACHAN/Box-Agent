"""Parent session thinking reaches both child execution strategies."""

from pathlib import Path

import pytest

from box_agent.agent import Agent
from box_agent.schema import FunctionCall, LLMResponse, StreamEvent, ToolCall
from box_agent.tools.file.read_tool import ReadTool
from box_agent.tools.sub_agent_tool import SubAgentTool


class DelegatingLLM:
    model = "test-model"
    max_output_tokens = 128

    def __init__(self, files=()):
        self.files = list(files)
        self.child_thinking = []

    async def generate(self, messages=None, **kwargs):
        if kwargs.get("call_kind") != "subagent_step":
            return LLMResponse(content='{"continue": false}', finish_reason="stop")
        self.child_thinking.append(kwargs["thinking_enabled"])
        return LLMResponse(content="child finished", finish_reason="stop")

    async def generate_stream(self, *, messages, **kwargs):
        if kwargs.get("call_kind") == "subagent_step":
            self.child_thinking.append(kwargs["thinking_enabled"])
            yield StreamEvent(type="text", delta="child finished")
            yield StreamEvent(type="finish", finish_reason="stop")
        elif messages[-1].role == "user":
            yield StreamEvent(type="finish", finish_reason="tool_use", tool_calls=[
                ToolCall(id=f"child-{len(self.child_thinking)}", type="function", function=FunctionCall(
                    name="sub_agent", arguments={"task": "Summarize the assigned material",
                                                  **({"files": self.files} if self.files else {})},
                )),
            ])
        else:
            yield StreamEvent(type="text", delta="parent finished")
            yield StreamEvent(type="finish", finish_reason="stop")


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True], ids=["general_loop", "batch_files"])
@pytest.mark.parametrize("initial", [True, False])
async def test_direct_agent_passes_current_thinking_to_children_across_turns(tmp_path, monkeypatch, batch, initial):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    source = tmp_path / "input.txt"
    source.write_text("Revenue is 42.")
    llm = DelegatingLLM([str(source)] if batch else [])
    read = ReadTool(workspace_dir=str(tmp_path))
    child = SubAgentTool(llm=llm, parent_tools={"read_file": read}, workspace_dir=str(tmp_path))
    agent = Agent(llm_client=llm, system_prompt="Be concise", tools=[read, child],
                  workspace_dir=str(tmp_path), thinking_enabled=initial, max_steps=3)
    for enabled in (initial, not initial):
        agent.thinking_enabled = enabled
        agent.add_user_message("Delegate this summary")
        events = [event async for event in agent.run_events()]
        assert events[-1].final_content == "parent finished"
    assert llm.child_thinking == [initial, not initial]


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_standalone_subagent_accepts_explicit_thinking(tmp_path, enabled):
    llm = DelegatingLLM()
    child = SubAgentTool(llm=llm, parent_tools={}, thinking_enabled=enabled)
    result = await child.execute(task="Summarize", required_tools=[])
    assert result.success
    assert llm.child_thinking == [enabled]
