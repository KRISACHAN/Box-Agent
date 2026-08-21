# AutoHOT Skill Optimized

这是 AutoHOT 汽车行业每日情报 Skill 的优化版技能包。

## 优化目标

本版本基于 AutoHOT 开发者页公开信息进行重构，重点补齐上一版短板：

- 渐进式加载；
- API 契约；
- 异常处理与降级；
- 交付契约；
- 数据质量与审计规则；
- 高频任务模板；
- 示例样例；
- SkillHub 上架所需的根入口 `SKILL.md`。

## 线上服务

默认线上 Base URL：

```text
https://autohot.coze.site
```

如运行环境提供以下配置，则优先使用显式配置：

```text
AUTOHOT_BASE_URL
COZE_PROJECT_DOMAIN_DEFAULT
AUTOHOT_API_TOKEN
```

当前公开页面展示的 API 主要位于 `/api/...` 路径下，响应结构为：

```json
{ "success": true, "data": {} }
```

## 目录结构

```text
autohot-skill-optimized/
├── SKILL.md
├── README.md
├── skill.json
├── package.json
├── references/
│   ├── api-contract.md
│   ├── error-handling.md
│   ├── delivery-contract.md
│   ├── data-quality-rules.md
│   └── workflow.md
├── templates/
│   ├── daily-brief.md
│   ├── analyst-briefing.md
│   ├── sales-morning-brief.md
│   ├── management-weekly-report.md
│   └── event-impact-analysis.md
└── examples/
    ├── daily-brief-example.md
    ├── company-tracking-example.md
    ├── no-data-example.md
    └── api-config-missing-example.md
```

## 使用方式

1. 首先读取根目录 `SKILL.md`。
2. 根据用户意图选择对应参考文档和模板。
3. 调用 AutoHOT API 时遵守 `references/api-contract.md`。
4. 接口失败、配置缺失或无数据时遵守 `references/error-handling.md`。
5. 生成文件或正式简报时遵守 `references/delivery-contract.md`。
6. 涉及判断、建议和来源时遵守 `references/data-quality-rules.md`。

## 高频任务

- 汽车行业日报；
- 分析师简报（核心信号、趋势洞察、关注事项）；
- 今日精选热点；
- 品牌/公司动态追踪；
- 赛道趋势分析；
- 销售晨会简报；
- 管理层周报；
- 单事件影响分析。

## 质量原则

- 不虚构新闻、来源、数据、实时性或文件路径；
- 明确说明是否为实时线上 AutoHOT 数据；
- 将事实、推断和建议分开；
- 把“未检到”与“事实不存在”区分开；
- 不提供投资买卖建议或法律最终意见；
- 对版权内容只做摘要和链接，不复刻全文。
