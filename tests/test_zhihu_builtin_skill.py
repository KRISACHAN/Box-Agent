from __future__ import annotations

import json
from pathlib import Path

from box_agent.tools.skill_loader import SkillLoader


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "box_agent" / "skills"


def test_zhihu_skill_is_whitelisted_and_discoverable_as_builtin() -> None:
    manifest = json.loads((SKILLS_ROOT / "_manifest.json").read_text(encoding="utf-8"))
    entries = {item["name"]: item["path"] for item in manifest["skills"]}

    assert entries["zhihu"] == "zhihu/SKILL.md"

    loader = SkillLoader(sources=[(SKILLS_ROOT, "builtin")])
    loader.discover_skills()
    skill = loader.get_skill("zhihu")

    assert skill is not None
    assert skill.source == "builtin"
    assert skill.skill_path == SKILLS_ROOT / "zhihu" / "SKILL.md"
    assert (SKILLS_ROOT / "zhihu" / "scripts" / "run.ps1").is_file()
    assert (SKILLS_ROOT / "zhihu" / "scripts" / "run.sh").is_file()


def test_zhihu_skill_uses_the_officev3_managed_cli_and_credentials() -> None:
    skill_root = SKILLS_ROOT / "zhihu"
    package_manifest = json.loads((skill_root / "manifest.json").read_text(encoding="utf-8"))
    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")

    assert package_manifest["distribution"] == {
        "mode": "host-bundled",
        "host": "officev3",
    }
    assert "update_manifest_url" not in package_manifest["cli"]
    assert "不要要求用户把 Secret 发送到对话中" in skill_text
    assert "第三方数据 → 其他 → 知乎" in skill_text

    for script_name in ("setup.ps1", "setup.sh"):
        setup_text = (skill_root / "scripts" / script_name).read_text(encoding="utf-8")
        assert "HOST_MANAGED_INSTALL" in setup_text
        assert "developer-cdn.zhihu.com" not in setup_text
