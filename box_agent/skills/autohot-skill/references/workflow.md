# 标准工作流程

## 1. 识别任务类型

先判断用户请求属于以下哪类：

- 每日行业日报；
- 销售晨会简报；
- 管理层周报；
- 品牌/公司追踪；
- 赛道/主题趋势；
- 单事件影响分析；
- 资讯搜索或事实核验。

## 2. 解析参数

提取并记录：

- 时间范围；
- 品牌、公司、车型或关键词；
- 赛道/分类；
- 受众：销售、管理层、市场、运营等；
- 输出形式：对话、Markdown、Word、Excel；
- 是否必须实时线上数据。

缺少非关键参数时可使用默认值，但必须在输出中说明。

## 3. 加载模块

根据任务类型按需加载：

| 任务 | 必读模块 |
|---|---|
| API 调用 | `references/api-contract.md`、`references/error-handling.md` |
| 日报 | `templates/daily-brief.md` |
| 销售晨会 | `templates/sales-morning-brief.md` |
| 管理层周报 | `templates/management-weekly-report.md` |
| 事件分析 | `templates/event-impact-analysis.md` |
| 文件交付 | `references/delivery-contract.md` |
| 质量审计 | `references/data-quality-rules.md` |

## 4. 获取数据

优先使用 AutoHOT 线上 API：

1. 确认 baseUrl；
2. 请求目标接口；
3. 检查 HTTP 状态码；
4. 检查 JSON 信封；
5. 检查数据时间范围；
6. 记录查询时间和限制。

## 5. 生成输出

按场景模板组织，不混淆事实、推断和建议。

## 6. 交付前自检

执行 `references/delivery-contract.md` 和 `references/data-quality-rules.md` 的验收清单。
