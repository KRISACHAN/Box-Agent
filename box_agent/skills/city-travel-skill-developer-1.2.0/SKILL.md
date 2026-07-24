---
name: city-travel-skill-developer
display_name: 城市旅行技能开发专家
version: 1.2.0
author: Shawn & Office Raccoon
tags:
  - skillhub
  - travel
  - city-research
  - evidence-map
  - prelaunch-qa
description: "把一个城市旅行主题开发成可安装、可上架预审的 SkillHub 技能包；适用于创建城市旅行助手、文化深度旅行助手、古都/博物馆/古建/非遗/城市生活方式 Skill，沉淀官方来源 source map、路线分支、实时核验、TRACE/Depth 评分、回归测试和白名单打包；不用于一次性普通行程规划、代订酒店机票、实时库存保证、博彩建议、签证法律咨询、医疗急救或绕过平台限制抓取内容。"
---

# 城市旅行技能开发专家

## 0. 北极星目标

把一个城市旅行主题开发成**能正确触发、能稳定规划、能说明证据来源、能处理实时不确定性、能通过 SkillHub 上架预审**的城市旅行 Skill 包。

本技能不是写一份城市攻略，而是生产一个可复用的城市旅行规划能力资产。完成时必须同时达到两类标准：

1. **结构合规完成**：根入口、YAML、README、package、知识库、模板、QA、脚本和 ZIP 结构符合 SkillHub 上传要求。
2. **专业能力完成**：城市核心资产、资料证据、路线分支、实时核验、边界拒答、模拟回归和上架前评估均已落地。

## 1. 何时使用

当用户提出以下需求时使用：

- 为某个城市定制旅行规划 Skill / 技能包。
- 把城市攻略、旅行 SOP、文旅资料、研学路线、Citywalk 玩法沉淀为 SkillHub 包。
- 开发古都、世界遗产、博物馆、古建、非遗、海丝、宗教、城市生活方式等文化深度旅行 Skill。
- 优化已有城市旅行 Skill，补 source map、回归测试、实时核验、上架门禁或干净 ZIP。
- 要求按照城市旅行技能开发 SOP、上架预审、TRACE/Depth 评估来做。

## 2. 何时不要使用

不要用于：

- 用户只要一次性旅行行程，不需要沉淀为 Skill。
- 用户要求代订酒店、机票、门票或承诺实时库存。
- 博彩、医疗急救、签证法律咨询、绕过平台限制抓取内容。
- 没有城市对象、没有可定义能力边界的泛旅游闲聊。

## 3. 输入检查

开始前检查：

| 输入 | 必要性 | 缺失处理 |
|---|---:|---|
| 城市名称 / 区域范围 | 必需 | 询问用户补充，或按用户指定项目名推断并标注假设 |
| 目标用户 | 推荐 | 默认覆盖初访、一日、两天、亲子、老人、摄影、低预算、美食导向 |
| SkillHub 发布目标 | 推荐 | 默认按上架预审候选包处理 |
| 输出目录 | 推荐 | 若用户指定，必须在指定目录承接；不得另建分散项目 |
| 资料来源 | 可选 | 优先官方/权威公开来源；缺口写入待核验项 |

若用户明确“完全自动”，除高风险操作和不可安全推断字段外，不反复请示。

## 4. 标准工作流

### Phase 1：城市类型诊断

判断城市属于哪类主导类型，可多选但必须排序：

- 世界遗产 / 古都 / 古建型
- 博物馆 / 研学型
- 非遗 / 手作 / 城市生活方式型
- 美食 / 夜游 / 消费型
- 自然风景 / 户外型
- 亲子 / 家庭友好型
- 交通中转 / 碎片时间型
- 综合度假 / 购物型

输出 `research/city-cultural-dossier.md` 或等价城市档案。

### Phase 2：官方证据与 source map

不得只写泛攻略。必须建立**证据型 source map**：

- 官方/权威来源：UNESCO、国家/地方文旅、文物、交通、景区官网/公众号、博物馆官网等。
- 强实时字段：开放时间、预约入口、票价、临时闭馆、交通管制、节假日服务。
- 使用边界：哪些事实可稳定使用，哪些必须提醒用户出行前复核。

模板见 `templates/evidence-source-map-template.md`。

### Phase 3：城市核心资产完整清单

对文化深度城市必须生成核心资产清单，不得只写概念。

示例：

- 世界遗产城市：遗产点完整清单、分组逻辑、游客理解路径。
- 古都城市：宫城/陵墓/寺院/博物馆/街区/遗址层级。
- 非遗城市：非遗项目、体验方式、预约/商业化边界。
- 美食城市：代表品类、街区、时间段、排队与替代方案。

沉淀到 `knowledge/cultural-assets-playbook.md` 和城市 Skill 的 `knowledge/`。

### Phase 4：路线分支与实时核验

必须把路线规划从“固定攻略”升级成“分支系统”：

- 时间分支：半天 / 一日 / 两天一晚 / 三天两晚。
- 人群分支：老人、亲子、摄影、低预算、美食、研学、轻松游。
- 天气分支：雨天、酷暑、台风、寒潮。
- 交通分支：高铁站、机场、口岸、停车、自驾、步行。
- 风险分支：闭馆、限流、拥堵、临时管制。

实时字段必须使用 `templates/realtime-check-template.md` 的保守口径。

### Phase 5：生成完整 SkillHub 包

推荐结构：

```text
city-skill-name/
├── SKILL.md
├── README.md
├── package.json
├── knowledge/
├── examples/
├── templates/
├── qa/
├── docs/
└── scripts/
```

根入口 `SKILL.md` 必须包含：

1. YAML front matter：`name` 必须是英文 slug。
2. 触发场景与排除场景。
3. 输入检查。
4. 工作流。
5. 输出契约。
6. 实时核验边界。
7. 质量门禁。
8. 资源索引。

### Phase 6：模拟回归矩阵

上架候选版至少 10 条回归，基础版至少 8 条。默认覆盖：

1. 初访游客一日游
2. 两天一晚经典线
3. 老人轻松游
4. 亲子研学
5. 雨天降级路线
6. 摄影 / 拍照路线
7. 低预算路线
8. 美食导向路线
9. 半天中转 / 碎片时间
10. 实时核验冲突处理
11. 高风险边界拒答
12. 资料不足时的澄清与保守输出

模板见 `templates/regression-matrix-template.md`。

### Phase 7：TRACE + Depth 评分

默认生成 `qa/trace-depth-scorecard.md`，判断是否达到：

- **85 / 80**：上架候选线。
- **90 / 90**：高分正式发布线。

评分必须说明证据、扣分点和 P0/P1/P2 整改建议。模板见 `templates/trace-depth-scorecard-template.md`。

### Phase 8：上架前增强 Sprint

正式打包前必须跑一轮增强：

1. source map 是否为证据型，而非结构型。
2. 城市核心资产清单是否完整。
3. 实时字段是否有官方核验入口和保守表述。
4. 回归记录是否达到数量和场景覆盖。
5. TRACE/Depth 是否给出明确判断。
6. `qa/prelaunch-review.md` 是否存在。

模板见 `playbooks/prelaunch-enhancement-sprint.md` 和 `templates/prelaunch-review-template.md`。

### Phase 9：白名单打包与污染扫描

严禁直接 zip 整个目录。必须使用白名单方式生成上传包。

允许进入 ZIP 的根文件：

- `SKILL.md`
- `README.md`
- `package.json`

允许目录：

- `knowledge/`
- `playbooks/` 或城市包中的路线文件
- `examples/`
- `templates/`
- `qa/`
- `docs/`
- `scripts/`
- `references/`

默认排除：隐藏文件、云同步上传态、`.gitignore`、独立 `LICENSE`、嵌套 ZIP、日志、临时文件、Word/Excel/PDF/图片等不支持上传文件。

执行 `scripts/validate_package.py <package-dir>` 后必须得到 `errors=0`。

## 5. 输出契约

标准交付至少包含：

```text
<city-skill-name>.zip
<city-skill-name>/SKILL.md
<city-skill-name>/README.md
<city-skill-name>/package.json
<city-skill-name>/qa/source-map.md
<city-skill-name>/qa/trace-depth-scorecard.md
<city-skill-name>/qa/regression-records.md
<city-skill-name>/qa/prelaunch-review.md
<city-skill-name>/scripts/validate_package.py
methodology-and-optimization-report.md
```

最终回复必须说明：

- 是否达到结构合规完成。
- 是否达到专业能力完成。
- TRACE/Depth 评分与是否过 85/80 或 90/90。
- P0/P1/P2 剩余问题。
- ZIP 与报告文件名。

## 6. P0/P1/P2 门禁

### P0：阻断项

出现任一项不得交付为上架候选：

- YAML front matter 缺失或不可解析。
- `name` 不是英文 slug。
- 根层没有 `SKILL.md`。
- ZIP 嵌套父目录或嵌套 ZIP。
- 出现隐藏文件、云同步上传态、`.gitignore`、独立 `LICENSE`。
- 出现本机绝对路径、用户名、密钥、内部资料路径。
- 出现内部历史摘要占位符。
- 声称能保证实时开放、票价、库存或预约。
- 误触发博彩、医疗、签证法律咨询等场景。

### P1：上架前强烈建议

- source map 为证据型。
- 至少 10 条模拟回归。
- 有 TRACE/Depth 评分。
- 有上架前核查报告。
- 官方来源与强实时字段有明确复核口径。

### P2：后续增强

- 增加真实用户试跑记录。
- 增加不同城市类型的资产清单模板。
- 增加无障碍、外籍游客、研学团等细分场景。
- 增加城市类型评分子项。

## 7. 长文件与历史摘要防护

写入长文件时不得复用工具历史中的内部摘要文本。交付前必须扫描：

- `Full tool-call argument omitted`
- `Full file content omitted`
- `Full tool output omitted`

验证脚本自身不得以完整连续字符串硬编码这些检测词，避免被外部扫描误报。

## 8. 资源索引

- 开发总流程：`playbooks/development-pipeline.md`
- 上架前增强：`playbooks/prelaunch-enhancement-sprint.md`
- 白名单打包：`playbooks/whitelist-packaging.md`
- source map 模板：`templates/evidence-source-map-template.md`
- TRACE/Depth 模板：`templates/trace-depth-scorecard-template.md`
- 回归矩阵模板：`templates/regression-matrix-template.md`
- 上架前核查模板：`templates/prelaunch-review-template.md`
- 污染扫描规则：`qa/artifact-contamination-check.md`
- 静态校验脚本：`scripts/validate_package.py`
