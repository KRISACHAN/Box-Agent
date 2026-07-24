import pytest

from scripts.generate_skills_manifest import (
    EXCLUDED_SKILL_DIRS,
    SKILLS_DIR,
    _collect_skills,
)


@pytest.mark.parametrize(
    "source_dir",
    [
        "city-travel-skill-developer-1.2.0",
        "city-travel-planner",
    ],
)
def test_city_travel_recommendations_stay_out_of_builtin_manifest(source_dir):
    assert (SKILLS_DIR / source_dir / "SKILL.md").is_file()
    assert source_dir in EXCLUDED_SKILL_DIRS
    assert all(
        not relative_path.startswith(f"{source_dir}/")
        for _, relative_path in _collect_skills()
    )
