# 源材料继承地图

本文件用于说明本技能包如何继承既有城市旅行 Skill 开发经验，以及从 `ljg-travel` 抽象出的深度文化旅行研究能力。

## 1. 既有城市旅行 Skill 开发资产

| 源材料 | 应进入的位置 | 转化形式 | 覆盖状态 |
|---|---|---|---|
| 澳门旅行规划助手开发经验 | `playbooks/development-pipeline.md`、`playbooks/source-distillation.md` | 资料蒸馏、行程分支、实时核验、异常降级 | 已覆盖 |
| 研发评审版 PRD | `SKILL.md`、`qa/quality-gate.md`、`templates/` | 开发流程、验收、输出契约、风险边界 | 已覆盖 |
| SkillHub 上架经验 | `scripts/validate_package.py`、`qa/quality-gate.md` | YAML、结构、隐藏文件、嵌套 ZIP、隐私检查 | 已覆盖 |

## 2. ljg-travel 可迁移能力

| 源材料 | 应进入的位置 | 转化形式 | 覆盖状态 |
|---|---|---|---|
| 考古学式案头研究 DBA | `playbooks/cultural-dba-research-playbook.md` | 文化深度型开发增强层 | 已覆盖 |
| 历史分层知识建模 | `knowledge/history-layers.md` | 城市历史阶段、可见遗存、参观点映射 | 已覆盖 |
| 博物馆 / 古建 / 考古遗址模型 | `knowledge/cultural-assets-playbook.md` | 文化资产知识卡与质量字段 | 已覆盖 |
| 深度内容发现筛选标准 | `knowledge/deep-content-discovery.md` | 视频、文章、社媒内容筛选与证据分级 | 已覆盖 |
| org-mode 研究底稿 | `research/city-cultural-dossier.md`、`templates/cultural-dossier-template.md` | Markdown 研究母稿模板 | 已覆盖 |
| 便携卡片产物 | `templates/civilization-overview-card-template.md`、`templates/route-quick-reference-card-template.md` | 手机速查卡 Markdown 模板 | 已覆盖 |
| denote 个人归档方式 | 不进入主包强制流程 | 仅保留为可选开发者归档思路，不写本机路径 | 已覆盖 |

## 3. PRD 落地检查

| PRD 要求 | 落地文件 | 状态 |
|---|---|---|
| 可复制城市旅行 Skill 开发流水线 | `SKILL.md`、`playbooks/development-pipeline.md` | 已覆盖 |
| 资料蒸馏与事实核验 | `playbooks/source-distillation.md`、`knowledge/deep-content-discovery.md` | 已覆盖 |
| 路线分支与场景适配 | `playbooks/route-branching.md` | 已覆盖 |
| 输出模板 | `templates/` | 已覆盖 |
| 质量门禁与发布校验 | `qa/quality-gate.md`、`scripts/validate_package.py` | 已覆盖 |
| 文化深度增强 | `playbooks/cultural-dba-research-playbook.md`、`knowledge/`、`research/` | 已覆盖 |

## 4. 未纳入项说明

- 不纳入任何本机绝对路径、个人用户名、云盘路径。
- 不纳入受版权保护内容的批量抓取方式。
- 不把图片、Word、Excel 等非必要文件放入 SkillHub 上传主包。
- 不把终端用户旅行研究流程原样搬进开发流程，而是抽象为开发增强模块。
## 5. 1.1.1 非文化与展示增强映射

| 新增需求 | 落地文件 | 转化形式 | 覆盖状态 |
|---|---|---|---|
| 海岛度假、购物、美食、户外徒步等非文化主导城市示例深度不足 | `playbooks/non-cultural-city-skill-playbook.md` | 场景分类、资料优先级、路线/安全/实时核验开发规则 | 已覆盖 |
| 非文化主导城市缺少可复用模板 | `templates/non-cultural-city-skill-template.md` | 可填充的 Skill 开发结构与质量字段 | 已覆盖 |
| 普通 SkillHub 用户需要更直观展示 | `examples/skillhub-before-after-showcase.md` | before/after 截图式说明、价值对比、上架页文案 | 已覆盖 |
| 需要一个完整城市样例包 | `examples/non-cultural-city-example-pack.md` | 海岛度假型目的地样例包、路线分支、核验清单 | 已覆盖 |

## 6. 1.1.2 购物型第二样例映射

| 新增需求 | 落地文件 | 转化形式 | 覆盖状态 |
|---|---|---|---|
| 非文化主导城市需要第二个非海岛完整样例 | `examples/shopping-city-example-pack.md` | 购物型目的地完整样例，覆盖商圈分层、退税/免税、品牌矩阵、价格时效、动线效率与预算风控 | 已覆盖 |
| 验证非文化模式不是单一海岛特例 | `SKILL.md`、`README.md` | 将购物型样例纳入资源索引和上架展示说明 | 已覆盖 |
