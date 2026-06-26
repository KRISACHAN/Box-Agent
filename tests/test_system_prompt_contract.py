from pathlib import Path


def test_system_prompt_keeps_todo_separate_from_factual_evidence():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "`plan_write` 表达“准备怎么做”" in prompt
    assert "不是进度追踪" in prompt
    assert "todo_write` 只记录执行进度" in prompt
    assert "不是事实证据、检索策略或结论来源" in prompt
    assert "完成一项立即标为 `completed`" in prompt
    assert "开始下一项前先把下一项标为 `in_progress`" in prompt
    assert "任务计划显示完成只代表步骤执行完毕，不代表事实已核实" in prompt


def test_system_prompt_requires_authoritative_sources_for_current_facts():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "Factual & Search Reliability" in prompt
    assert "必须按今天日期检索或核对当前权威来源" in prompt
    assert "优先使用官方公告、模型卡、开发者文档、透明度页面或权威一手来源" in prompt
    assert "不要用“公开资料不多”替代答案" in prompt


def test_system_prompt_separates_source_content_from_search_clues():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "只有成功读取该 URL/文件/原始材料正文" in prompt
    assert "才可声称“已读到原文/完整内容”" in prompt
    assert "`web_search` 搜索结果、标题、摘要、转载页或相近内容只能作为线索" in prompt
    assert "不能替代原文" in prompt
    assert "明确说明失败原因和证据缺口" in prompt
    assert "禁止把它包装成对原文的总结、核对或引用" in prompt
    assert "只有对应工具成功返回目标内容时，才可这样表述" in prompt


def test_system_prompt_sub_agent_trigger_covers_separable_evidence_units():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "可隔离的小单元任务" in prompt
    assert "分别收集证据、核验事实、分析判断、起草内容或检查质量" in prompt
    assert "候选项、来源范围、时间段" in prompt
    assert "不限于写作或 QA" in prompt
    assert "只返回局部证据/结论" in prompt
    assert "最终合并、交叉校验" in prompt
