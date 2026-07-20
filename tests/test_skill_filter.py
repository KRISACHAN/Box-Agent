"""Tests for keyword-based skill filtering (SkillLoader.filter_by_query
and SkillSelector)."""

from __future__ import annotations

import pytest

from box_agent.tools.skill_loader import (
    SKILL_SLOT_SENTINEL,
    Skill,
    SkillLoader,
    SkillSelector,
    _tokenize,
)


@pytest.fixture
def loader() -> SkillLoader:
    inst = SkillLoader.__new__(SkillLoader)
    inst._sources = []
    inst.loaded_skills = {
        "memory-guide": Skill(
            name="memory-guide",
            description="proactive memory hints",
            content="",
            source="builtin",
        ),
        "lark-mail": Skill(
            name="lark-mail",
            description="飞书邮箱 draft compose send 邮件",
            content="",
            source="user",
            keywords=["邮件", "邮箱", "mail"],
        ),
        "pptx": Skill(
            name="pptx",
            description="PowerPoint slide deck 演示文稿 PPT",
            content="",
            source="builtin",
            keywords=["ppt", "pptx", "幻灯片"],
            required_skills=["html-templates"],
            related_skills=["research-synthesis", "research-to-deck-outline"],
        ),
        "html-templates": Skill(
            name="html-templates",
            description="visual style template profiles for HTML and slides",
            content="",
            source="builtin",
            keywords=["template", "visual", "style", "视觉风格"],
        ),
        "hyperframes-video": Skill(
            name="hyperframes-video",
            description=(
                "HyperFrames MP4/GIF videos; motion graphics; explainer clips; "
                "视频、短片、动图、动画成片。"
            ),
            content="",
            source="builtin",
            keywords=[
                "video",
                "videos",
                "mp4",
                "gif",
                "animation",
                "hyperframes",
                "motion-graphics",
                "explainer-clip",
                "视频",
                "动画",
                "短片",
                "动图",
            ],
            related_skills=["html-templates"],
        ),
        "xlsx": Skill(
            name="xlsx",
            description="Excel spreadsheet 表格",
            content="",
            source="builtin",
            keywords=["excel", "表格", "xlsx"],
        ),
        "research-synthesis": Skill(
            name="research-synthesis",
            description="industry analysis market research 深度总结 行业研究",
            content="",
            source="builtin",
            keywords=["行业分析", "行业研究", "市场研究", "深度总结", "资料综述"],
        ),
        "research-to-deck-outline": Skill(
            name="research-to-deck-outline",
            description="turn research into a slide-by-slide PPT outline",
            content="",
            source="builtin",
            keywords=["ppt outline", "页面结构", "逐页大纲"],
        ),
    }
    return inst


class TestTokenize:
    def test_empty(self):
        assert _tokenize("") == set()
        assert _tokenize("   ") == set()

    def test_english_short_words_dropped(self):
        # length < 2 drops single chars
        assert _tokenize("a hi") == {"hi"}

    def test_chinese_sliding_window(self):
        toks = _tokenize("发邮件")
        assert "发邮件" in toks
        assert "邮件" in toks
        assert "发邮" in toks

    def test_mixed(self):
        toks = _tokenize("做个PPT")
        assert "ppt" in toks
        assert "做个" in toks


class TestFilterByQuery:
    def test_greeting_returns_only_always_on(self, loader: SkillLoader):
        # "hi" / "你好" must NOT trigger the full catalog. This is the
        # critical case the user explicitly called out.
        for greeting in ["hi", "你好", "hello", "在吗"]:
            out = loader.filter_by_query(greeting)
            assert [s.name for s in out] == ["memory-guide"], greeting

    def test_empty_query_returns_only_always_on(self, loader: SkillLoader):
        for q in ["", None, "   "]:
            out = loader.filter_by_query(q)
            assert [s.name for s in out] == ["memory-guide"]

    def test_ppt_query_matches_pptx(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("帮我做个PPT")]
        assert "pptx" in names
        assert "html-templates" in names
        assert "research-synthesis" in names
        assert "research-to-deck-outline" in names
        assert "memory-guide" in names
        assert "lark-mail" not in names

    def test_mail_query_matches_lark_mail(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("发个邮件给老板")]
        assert "lark-mail" in names
        assert "pptx" not in names

    def test_excel_query_matches_xlsx(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("分析excel数据")]
        assert "xlsx" in names

    def test_video_query_matches_hyperframes_video(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("帮我做一个方块掉落的视频")]
        assert "hyperframes-video" in names
        assert "html-templates" in names
        assert "pptx" not in names

    def test_mp4_query_matches_hyperframes_video(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("render this animation as mp4")]
        assert "hyperframes-video" in names

    @pytest.mark.parametrize(
        "query",
        [
            "生成一张海报",
            "生成一个PPT",
            "帮我做一个网页",
            "把这个页面改一下",
            "导出 PDF",
            "render this chart",
            "create a landing page",
        ],
    )
    def test_non_video_deliverables_do_not_match_hyperframes_video(
        self,
        loader: SkillLoader,
        query: str,
    ):
        names = [s.name for s in loader.filter_by_query(query)]
        assert "hyperframes-video" not in names

    def test_industry_research_query_matches_research_synthesis(
        self, loader: SkillLoader
    ):
        names = [s.name for s in loader.filter_by_query("做一个行业分析和深度总结")]
        assert "research-synthesis" in names
        assert "webapp-testing" not in names

    def test_no_match_returns_only_always_on(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("随便聊聊天气")]
        assert names == ["memory-guide"]

    def test_max_skills_caps_results(self, loader: SkillLoader):
        # Add a few synthetic skills that all match "数据"
        for i in range(10):
            loader.loaded_skills[f"data-{i}"] = Skill(
                name=f"data-{i}",
                description="数据 数据 数据",
                content="",
                source="builtin",
                keywords=["数据"],
            )
        out = loader.filter_by_query("数据", max_skills=3)
        # 3 matched + always_on
        assert len(out) == 4

    def test_default_max_skills_is_16(self, loader: SkillLoader):
        for i in range(20):
            loader.loaded_skills[f"data-{i:02d}"] = Skill(
                name=f"data-{i:02d}",
                description="数据",
                content="",
                source="builtin",
                keywords=["数据"],
            )
        out = loader.filter_by_query("数据")
        # 16 matched + always_on
        assert len(out) == 17

    def test_required_and_related_skills_expand_one_hop(self, loader: SkillLoader):
        names = [s.name for s in loader.filter_by_query("PPT")]
        assert names.index("pptx") < names.index("html-templates")
        assert "research-synthesis" in names
        assert "research-to-deck-outline" in names

    def test_keywords_outweigh_description(self, loader: SkillLoader):
        # "幻灯片" is in pptx keywords (weight 3) but not in any description
        names = [s.name for s in loader.filter_by_query("做幻灯片")]
        assert "pptx" in names


class TestSkillSelector:
    def _build_prompt(self) -> str:
        return f"PREFIX\n\n{SKILL_SLOT_SENTINEL}\n\nSUFFIX"

    def test_unbound_returns_none(self, loader: SkillLoader):
        sel = SkillSelector(loader)
        assert sel.update("hi") is None
        assert not sel.bound

    def test_bind_without_sentinel_stays_unbound(self, loader: SkillLoader):
        sel = SkillSelector(loader)
        sel.bind("no sentinel here")
        assert not sel.bound

    def test_bind_extracts_prefix_and_suffix(self, loader: SkillLoader):
        sel = SkillSelector(loader)
        sel.bind(self._build_prompt())
        assert sel.bound

    def test_greeting_renders_only_always_on(self, loader: SkillLoader):
        sel = SkillSelector(loader)
        sel.bind(self._build_prompt())
        out = sel.update("hi")
        assert out is not None
        assert "memory-guide" in out
        assert "pptx" not in out
        assert "lark-mail" not in out

    def test_cumulative_query_grows_skill_set(self, loader: SkillLoader):
        sel = SkillSelector(loader)
        sel.bind(self._build_prompt())

        out1 = sel.update("hi")
        assert "pptx" not in out1
        assert sel.matched_skill_names == ("memory-guide",)

        out2 = sel.update("帮我做PPT")
        assert "pptx" in out2
        assert "pptx" in sel.matched_skill_names

        # Adding a mail intent on a later turn should keep pptx (cumulative)
        out3 = sel.update("再发个邮件给老板")
        assert "pptx" in out3
        assert "lark-mail" in out3
        assert "lark-mail" in sel.matched_skill_names

    def test_repeated_query_returns_none(self, loader: SkillLoader):
        sel = SkillSelector(loader)
        sel.bind(self._build_prompt())
        sel.update("帮我做PPT")
        # No change — nothing new in the cumulative skill set
        assert sel.update("继续做这个PPT") is None
        assert "pptx" in sel.matched_skill_names

    def test_rebind_resets_signature(self, loader: SkillLoader):
        """After session-mode mid-session rewrite, re-binding to a fresh
        prompt with the sentinel should force the next update() to
        materialize again (not silently return None)."""
        sel = SkillSelector(loader)
        sel.bind(self._build_prompt())
        sel.update("PPT")
        # Simulate _apply_session_mode replacing messages[0]
        sel.bind(f"NEWPREFIX\n\n{SKILL_SLOT_SENTINEL}\n\nNEWSUFFIX")
        out = sel.update("PPT")
        assert out is not None
        assert "NEWPREFIX" in out
        assert "pptx" in out
