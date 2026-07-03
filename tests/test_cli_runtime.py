"""CLI-mode runtime wiring tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import box_agent.cli as cli
from box_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from box_agent.schema import LLMResponse, StreamEvent
from box_agent.tools.skill_loader import SkillLoader
from box_agent.tools.runtime import build_skill_runtime_context, build_skill_runtime_prompt
from box_agent.tools.setup import add_workspace_tools


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def _write_skill(
    skills_dir: Path,
    name: str,
    *,
    description: str,
    keywords: list[str],
    content: str,
    required_skills: list[str] | None = None,
) -> None:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    required = (
        f"required_skills: [{', '.join(required_skills)}]\n"
        if required_skills
        else ""
    )
    skill_dir.joinpath("SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"keywords: [{', '.join(keywords)}]\n"
        f"{required}"
        "---\n"
        f"{content}\n",
        encoding="utf-8",
    )


class _CaptureStreamLLM:
    instances: list["_CaptureStreamLLM"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.system_prompts: list[str] = []
        self.retry_callback = None
        self.instances.append(self)

    async def generate(self, *args, **kwargs):
        return LLMResponse(content="ok", finish_reason="stop")

    async def generate_stream(self, *, messages, **kwargs):
        self.system_prompts.append(messages[0].content)
        yield StreamEvent(type="text", delta="done.")
        yield StreamEvent(type="finish", finish_reason="stop")


def test_cli_workspace_tools_receive_self_managed_node_runtime(tmp_path: Path) -> None:
    node_root = tmp_path / ".box-agent" / "runtimes" / "node"
    node_bin = node_root / "versions" / "node-v22-test-darwin-arm64" / "bin"
    node = node_bin / "node"
    npm = node_bin / "npm"
    npx = node_bin / "npx"
    for path in (node, npm, npx):
        _make_executable(path)
    node_root.mkdir(parents=True, exist_ok=True)
    (node_root / "manifest.json").write_text(
        json.dumps(
            {
                "active": {
                    "version": "v22-test",
                    "node": str(node),
                    "npm": str(npm),
                    "npx": str(npx),
                }
            }
        ),
        encoding="utf-8",
    )

    runtime_context = build_skill_runtime_context(
        sandbox_mode=False,
        node_runtime_root=node_root,
    )
    tools = []
    add_workspace_tools(
        tools,
        Config(
            llm=LLMConfig(api_key="test-key"),
            agent=AgentConfig(workspace_dir=str(tmp_path / "workspace")),
            tools=ToolsConfig(enable_file_tools=False, enable_todo=False),
        ),
        tmp_path / "workspace",
        sandbox_mode=False,
        output=lambda _msg: None,
        skill_runtime_context=runtime_context,
    )

    bash_tool = next(tool for tool in tools if tool.name == "bash")
    assert bash_tool._subprocess_env["BOX_AGENT_NODE"] == str(node)
    assert bash_tool._subprocess_env["BOX_AGENT_NPM"] == str(npm)
    assert bash_tool._subprocess_env["BOX_AGENT_NPX"] == str(npx)
    assert bash_tool._subprocess_env["NODE_PATH"] == str(node_root / "sandbox" / "node_modules")
    assert bash_tool._subprocess_env["npm_config_cache"] == str(node_root / "sandbox" / "npm-cache")
    assert bash_tool._subprocess_env["npm_config_prefix"] == str(node_root / "sandbox" / "npm-prefix")

    prompt = build_skill_runtime_prompt(runtime_context)
    assert "- Node:" in prompt
    assert "via `$BOX_AGENT_NODE`" in prompt
    assert "$BOX_AGENT_NODE" in prompt


def test_cli_task_preloads_pptx_even_when_filter_drops_it(tmp_path: Path, monkeypatch) -> None:
    skills_dir = tmp_path / "skills"
    prompt = "做一份 12 页新员工入职培训 PPT，1920×1080 可编辑"
    for index in range(16):
        _write_skill(
            skills_dir,
            f"lark-noise-{index}",
            description="做一份 新员工 入职 培训 可编辑 会议室 HR 友好 流程 清单",
            keywords=["做一份", "新员工", "入职", "培训", "可编辑", "会议室", "HR"],
            content=f"# Noise {index}",
        )
    _write_skill(
        skills_dir,
        "pptx",
        description="Create editable PowerPoint PPTX slide decks.",
        keywords=["ppt", "pptx", "powerpoint", "slide"],
        required_skills=["html-templates"],
        content="# PPTX FULL RULES\nUse the editable deck workflow.",
    )
    _write_skill(
        skills_dir,
        "html-templates",
        description="Select visual style constraints for HTML slide decks.",
        keywords=["html", "template", "visual"],
        content="# HTML TEMPLATE RULES\nSelect a Visual DNA profile.",
    )
    skill_loader = SkillLoader(skills_dir)
    skill_loader.discover_skills()
    assert "pptx" not in [skill.name for skill in skill_loader.filter_by_query(prompt)]

    config_path = tmp_path / "config.yaml"
    config_path.write_text("api_key: test\n", encoding="utf-8")
    system_prompt_path = tmp_path / "system_prompt.md"
    system_prompt_path.write_text(
        "base system\n\n{SKILLS_METADATA}\n\n{SANDBOX_INFO}",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(
            max_steps=1,
            workspace_dir=str(workspace),
            enable_memory=False,
            enable_memory_extraction=False,
            memory_maintainer_enabled=False,
            memory_promotion_proposal_enabled=False,
            system_prompt_path=str(system_prompt_path),
        ),
        tools=ToolsConfig(
            enable_file_tools=False,
            enable_bash=False,
            enable_todo=False,
            enable_plan=False,
            enable_sub_agent=False,
            enable_mcp=False,
            enable_skills=True,
            allow_full_access=True,
        ),
    )

    async def fake_initialize_base_tools(*args, **kwargs):
        return [], skill_loader, None

    monkeypatch.setattr(cli.Config, "get_default_config_path", staticmethod(lambda: config_path))
    monkeypatch.setattr(cli.Config, "from_yaml", staticmethod(lambda _path: config))
    monkeypatch.setattr(
        cli.Config,
        "find_config_file",
        staticmethod(lambda name: Path(name) if name == str(system_prompt_path) else None),
    )
    monkeypatch.setattr(cli, "LLMClient", _CaptureStreamLLM)
    monkeypatch.setattr(cli, "initialize_base_tools", fake_initialize_base_tools)
    monkeypatch.setattr(cli, "add_workspace_tools", lambda *args, **kwargs: None)
    _CaptureStreamLLM.instances.clear()

    exit_code = asyncio.run(
        cli.run_agent(
            workspace,
            task=prompt,
            sandbox_mode=False,
            verify_api=False,
            goal_autopilot_enabled=False,
        )
    )

    assert exit_code == 0
    first_system_prompt = _CaptureStreamLLM.instances[0].system_prompts[0]
    assert "## Auto-Loaded Skill Instructions" in first_system_prompt
    assert "# Skill: pptx" in first_system_prompt
    assert "# PPTX FULL RULES" in first_system_prompt
    assert "# Skill: html-templates" in first_system_prompt
    assert "# HTML TEMPLATE RULES" in first_system_prompt
