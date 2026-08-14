from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from box_agent.tools.skill_loader import SkillLoader
from box_agent.tools.skill_preload import (
    build_auto_loaded_skills_prompt,
    host_runtime_preload_skill_names,
)


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "box_agent" / "skills"


def test_browser_use_skill_is_packaged_as_builtin() -> None:
    manifest = json.loads((SKILLS_ROOT / "_manifest.json").read_text(encoding="utf-8"))
    entries = {item["name"]: item for item in manifest["skills"]}

    assert entries["browser-use"] == {
        "name": "browser-use",
        "path": "browser-use/SKILL.md",
    }

    loader = SkillLoader(sources=[(SKILLS_ROOT, "builtin")])
    loader.discover_skills()
    skill = loader.get_skill("browser-use")

    assert skill is not None
    assert skill.source == "builtin"
    assert skill.skill_path == SKILLS_ROOT / "browser-use" / "SKILL.md"


@pytest.mark.parametrize(
    "query",
    [
        "用系统浏览器打开这个网址",
        "读取当前页面",
        "后台抓取这个网页",
        "use my current browser login",
    ],
)
def test_browser_use_skill_matches_browser_intent(query: str) -> None:
    loader = SkillLoader(sources=[(SKILLS_ROOT, "builtin")])
    loader.discover_skills()

    matched_names = {
        skill.name for skill in loader.filter_by_query(query, max_skills=20)
    }

    assert "browser-use" in matched_names


def test_browser_intent_preloads_full_builtin_instructions() -> None:
    query = "用我当前登录的真实浏览器打开这个网站"
    loader = SkillLoader(sources=[(SKILLS_ROOT, "builtin")])
    loader.discover_skills()
    matched_names = tuple(skill.name for skill in loader.filter_by_query(query))

    preload_names = host_runtime_preload_skill_names(
        matched_names,
        SimpleNamespace(
            browser_tools=SimpleNamespace(available=True),
            browser_connector=SimpleNamespace(available=True),
        ),
        query,
    )
    rendered = build_auto_loaded_skills_prompt(
        loader,
        "base system",
        preload_names,
    )

    assert rendered.loaded_names == ("browser-use",)
    assert "受管浏览器自动化" in rendered.system_prompt
    assert "可见真实浏览器" in rendered.system_prompt
    assert 'mcp_config(action="update", name="playwright"' in rendered.system_prompt
    assert "禁止新增 `playwright-headed`" in rendered.system_prompt
    assert 'mcp_config(action="inspect_browser")' in rendered.system_prompt
    assert "默认固定无头" not in rendered.system_prompt
    assert "不要把两者视为同义词" in rendered.system_prompt
    assert "不要仅凭“看到窗口”断言使用了真实浏览器" in rendered.system_prompt
