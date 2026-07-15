import pytest

from box_agent.core import _maybe_summarize
from box_agent.schema import LLMResponse, Message
from box_agent.tools.skill_loader import SkillLoader
from box_agent.tools.skill_preload import (
    ACTIVE_SKILLS_HEADING,
    AUTO_LOADED_SKILLS_HEADING,
    build_active_skills_prompt,
    build_auto_loaded_skills_prompt,
    strip_active_skills,
)


class SummaryLLM:
    async def generate(self, messages, tools=None, **kwargs) -> LLMResponse:
        return LLMResponse(content="Execution summary", finish_reason="stop")


def test_active_skills_render_once_at_system_prompt_tail() -> None:
    skill_prompt = "# Skill: pptx\n\nFollow the PPT workflow."

    rendered = build_active_skills_prompt("base system", {"pptx": skill_prompt})
    rendered_again = build_active_skills_prompt(rendered, {"pptx": skill_prompt})

    assert rendered_again == rendered
    assert rendered.count(ACTIVE_SKILLS_HEADING) == 1
    assert rendered.endswith(skill_prompt)
    assert strip_active_skills(rendered) == "base system"


def test_active_skills_replace_changed_content_by_name() -> None:
    first = build_active_skills_prompt(
        "base system",
        {"pptx": "# Skill: pptx\n\nOld instructions."},
    )
    updated = build_active_skills_prompt(
        first,
        {"pptx": "# Skill: pptx\n\nNew instructions."},
    )

    assert "Old instructions." not in updated
    assert updated.endswith("New instructions.")


def test_auto_loaded_skills_stay_before_existing_active_skills(tmp_path) -> None:
    skill_dir = tmp_path / "pptx"
    skill_dir.mkdir()
    skill_dir.joinpath("SKILL.md").write_text(
        "---\nname: pptx\ndescription: Build decks\n---\n\nAUTO_RULE",
        encoding="utf-8",
    )
    loader = SkillLoader(tmp_path)
    loader.discover_skills()
    active_prompts = {"manual": "# Skill: manual\n\nACTIVE_RULE"}
    active_system = build_active_skills_prompt("base system", active_prompts)

    auto_result = build_auto_loaded_skills_prompt(
        loader,
        active_system,
        ["pptx"],
    )
    final_prompt = build_active_skills_prompt(
        auto_result.system_prompt,
        active_prompts,
    )

    assert final_prompt.index(AUTO_LOADED_SKILLS_HEADING) < final_prompt.index(
        ACTIVE_SKILLS_HEADING
    )
    assert "AUTO_RULE" in final_prompt
    assert final_prompt.endswith("ACTIVE_RULE")


@pytest.mark.asyncio
async def test_layer_two_summary_preserves_active_skills_in_system_prompt() -> None:
    active_system = build_active_skills_prompt(
        "base system",
        {"pptx": "# Skill: pptx\n\nMANDATORY_SKILL_RULE"},
    )
    messages = [
        Message(role="system", content=active_system),
        Message(role="user", content="build a deck"),
        Message(role="assistant", content="working"),
        Message(
            role="tool",
            name="bash",
            tool_call_id="tool-1",
            content="x" * 500,
        ),
    ]

    summarized, _, _ = await _maybe_summarize(
        SummaryLLM(),
        messages,
        token_limit=1,
        api_total_tokens=0,
        skip_check=False,
    )

    assert summarized is not None
    assert "MANDATORY_SKILL_RULE" in summarized[0].content
    assert summarized[0].content.endswith("MANDATORY_SKILL_RULE")
