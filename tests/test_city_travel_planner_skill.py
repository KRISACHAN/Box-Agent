from pathlib import Path

import pytest

from box_agent.tools.skill_loader import SkillLoader


SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "box_agent"
    / "skills"
    / "city-travel-planner"
)


@pytest.fixture
def loader():
    skill_loader = SkillLoader(sources=[(SKILL_DIR, "builtin")])
    skill_loader.discover_skills()
    return skill_loader


@pytest.mark.parametrize(
    "query",
    [
        "去恩施旅游 5天怎么玩",
        "去恩施旅行五天，公共交通为主怎么安排",
        "第一次去北京，带父母四天住哪里方便",
        "上海周末两日旅游攻略，不想来回跑",
        "三亚亲子 5 天游，预算中等，怕下雨",
        "京都大阪六天怎么分配",
        "贵州自驾七日路线怎么排",
        "厦门半天中转怎么玩才不误车",
    ],
)
def test_city_travel_planner_matches_travel_requests(loader, query):
    matches = loader.filter_by_query(query, always_on=frozenset())

    assert [skill.name for skill in matches] == ["city-travel-planner"]


def test_city_travel_planner_resources_exist(loader):
    skill = loader.get_skill("city-travel-planner")

    assert skill is not None
    assert not skill.broken
    resource_paths = [
        "references/destination-types.md",
        "references/itinerary-output.md",
        "references/route-planning.md",
        "references/research-and-verification.md",
        "examples/prompts.md",
        "qa/regression-prompts.md",
    ]
    for relative_path in resource_paths:
        assert (SKILL_DIR / relative_path).is_file()
    assert str(SKILL_DIR / "references/itinerary-output.md") in skill.content
