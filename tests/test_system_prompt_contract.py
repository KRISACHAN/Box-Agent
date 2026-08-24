from pathlib import Path


def test_system_prompt_forbids_plaintext_user_credentials():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "不得在回复、日志、命令参数或交付产物中明文显示用户提供的" in prompt
    assert "API Key、Access Token、Secret、密码等敏感凭据" in prompt
    assert "确需引用时仅显示脱敏片段" in prompt


def test_system_prompt_leaves_ambiguous_path_resolution_to_the_model():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "相对路径由工具从当前 active project/artifact root 解析" in prompt
    assert "不要假定始终相对 workspace" in prompt
    assert "由模型自行推断并尝试范围明确的具体候选路径" in prompt
    assert "不要通过递归搜索整个用户主目录来定位文件" in prompt
    assert "合理候选均失败后再询问用户" in prompt
    assert "使用绝对路径或相对 workspace 的路径" not in prompt
    assert "例如 `~/Downloads/...`" not in prompt


def test_system_prompt_distinguishes_missing_attachments_from_explicit_paths():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "任务明确依赖用户尚未提供的附件" in prompt
    assert "用户已经给出路径或位置时" in prompt
    assert "先按当前路径与权限语义调用工具验证" in prompt
    assert "不要仅因缺少附件元信息就把请求判定为缺失输入" in prompt
    assert "所有文件相关请求一律视为缺失输入" not in prompt


def test_system_prompt_keeps_todo_separate_from_factual_evidence():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "`plan_write` 表达“准备怎么做”" in prompt
    assert "不是进度追踪" in prompt
    assert "不含新任务的确认词而新建 plan" in prompt
    assert "todo_write` 只记录执行进度" in prompt
    assert "不是事实证据、检索策略或结论来源" in prompt
    assert "完成并验证后立即用 `transition` 推进" in prompt
    assert "已有 plan，新建或重建 todo 前必须先调用 `plan_read`" in prompt
    assert "todo 必须按 `plan.steps` 的原顺序派生" in prompt
    assert "先用 `plan_write` 把 plan 标为 `revised`" in prompt
    assert "初始化清单或 plan 实质修订后" in prompt
    assert "正常推进用 `action=\"transition\"`" in prompt
    assert "为未变化的已有 Todo 保留 `id`" in prompt
    assert "首次初始化 Todo 时不要传 `id`" in prompt
    assert "Plan step 的 `id` 不是 Todo `id`" in prompt
    assert "列表为空或全部完成时允许没有 `in_progress`" in prompt
    assert "否则必须恰好有一个 `in_progress`" in prompt
    assert "只执行唯一的 `in_progress` 项" in prompt
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


def test_system_prompt_forbids_reusing_model_history_placeholders():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "[Full tool-call argument omitted from model history]" in prompt
    assert "是内部历史摘要，不是真实文件内容" in prompt
    assert "绝不能复制到任何工具参数" in prompt
    assert "不要为绕过摘要保护而改用 `execute_code`" in prompt


def test_system_prompt_routes_large_jsonl_to_bounded_query_tool():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "JSONL/NDJSON" in prompt
    assert "使用 `query_jsonl` 做字段投影和游标分页" in prompt
    assert "不要因 JSONL 超长记录改用 `execute_code` 整体读取" in prompt


def test_system_prompt_uses_mode_specific_file_delivery_guidance():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "{FILE_DELIVERY_INFO}" in prompt
    assert "local-file://C:/" not in prompt
    assert "所有交付物落 `{workspace}/output/`" not in prompt


def test_system_prompt_sub_agent_routing_uses_flat_fail_closed_contract():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "独立上下文、并行耗时或证据隔离收益明显高于启动和合并成本" in prompt
    assert "不要仅因单元数量达到 5 个就强制并行" in prompt
    assert "`required_tools`、`skills`、`files`、`write_scope` 和 `budget`" in prompt
    assert "不要构造 `execution/capabilities/inputs/constraints` 嵌套对象" in prompt
    assert "运行时自动使用有完整性校验的批处理" in prompt
    assert "可信本地只读工具" in prompt
    assert "进程工具、外部副作用和未知 MCP 默认拒绝" in prompt
    assert "最终交付物与最终验证始终由主 Agent 完成" in prompt
    assert '`budget` 必须直接传对象' in prompt
    assert '`write_scope=["research/dim01.md"]`' in prompt
    assert "并行子 Agent 的范围必须互斥" in prompt


def test_system_prompt_makes_missing_input_a_resumable_pause():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "调用一次 `request_user_input`" in prompt
    assert "只问一个聚焦问题并列出最少必要字段" in prompt
    assert "用户补充后从当前检查点继续" in prompt
    assert "可省略或可标为待补充的非必要内容不得阻塞" in prompt


def test_system_prompt_separates_user_decisions_from_missing_input():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "调用 `request_user_decision`" in prompt
    assert "不要只在普通文本里列方案并等待回复" in prompt
    assert "内部实现和恢复策略应自行选择" in prompt
    assert "最终是否允许由运行时决定" in prompt
    assert "安全主路径优先推进" in prompt
    assert "不改变用户可见结果时直接推进，不弹卡" in prompt
    assert "将该路径设为默认项并申请 15-30 秒超时自动提交" in prompt
    assert "必须等待人工选择" in prompt


def test_system_prompt_checks_explicit_requirements_before_claiming_completion():
    prompt = Path("box_agent/config/system_prompt.md").read_text(encoding="utf-8")

    assert "产物文件存在不等于用户要求已经满足" in prompt
    assert "逐项核对用户明确要求的内容、数据、时效和格式" in prompt
    assert "搜索链接、占位符或“请自行查看”不能冒充已取得的实时结果" in prompt
    assert "明确标记未完成及其证据缺口，不得宣称任务已完成" in prompt
