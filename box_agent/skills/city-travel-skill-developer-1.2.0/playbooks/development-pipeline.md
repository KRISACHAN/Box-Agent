# Playbook：城市旅行 Skill 开发流水线

## 0. 北极星

把一个城市旅行主题开发成可安装、可触发、可稳定回答、可上架预审的 SkillHub 包。

## 1. Intake：定义城市与用户场景

必须明确：

- 城市或区域；
- 目标用户：首次到访、亲子、情侣、银发、拍照、深度游、商务顺路等；
- 出行时长：半日、一日、两天一晚、多日；
- 入口与交通：机场、车站、口岸、码头、自驾、地铁；
- 预算层级；
- 是否需要实时核验。

缺失信息可默认，但必须标注假设。不能因为用户没有给全信息就停住，除非城市对象本身不明确。

## 2. Research Map：建立资料地图

输出 `qa/source-map.md`，至少包含：

| 来源类型 | 例子 | 用途 | 风险 |
|---|---|---|---|
| 官方文旅/交通 | 文旅局、机场、地铁、景区官网 | 事实与核验入口 | 页面更新、节假日调整 |
| 官方票务/场馆 | 博物馆、展馆、演出官网 | 开放、预约、票务 | 库存实时变化 |
| 商业综合体/酒店 | 商场、度假区、酒店官网 | 体验与接驳 | 班次和活动变化 |
| 用户资料 | 用户上传攻略、访谈、历史问答 | 场景与痛点 | 代表性不足 |
| 社媒攻略 | 小红书、公众号、社区经验 | 表达线索和避坑 | 不可当作权威事实 |

## 3. Distillation：资料蒸馏

把资料转为规则，而不是堆叠链接：

- 区域关系：哪些点可以顺路，哪些点不应硬塞；
- 时间成本：交通、排队、拍照、吃饭、带娃休息；
- 人群适配：亲子、老人、拍照、预算敏感；
- 替代方案：雨天、太热、排队长、临时闭馆；
- 核验字段：营业、票务、班次、预约、活动。

## 4. Architecture：生成包结构

推荐 release-ready 结构：

```text
<city-travel-skill>/
├── SKILL.md
├── README.md
├── package.json
├── knowledge/
│   ├── index.md
│   ├── city-profile.md
│   ├── transportation-and-entry.md
│   ├── audience-scenarios.md
│   ├── route-branches-and-exceptions.md
│   └── real-time-verification.md
├── examples/
│   ├── index.md
│   ├── one-day-easy.md
│   ├── family-two-days.md
│   └── photo-social-guide.md
├── templates/
│   ├── itinerary-output-template.md
│   ├── regression-record-template.md
│   └── real-time-verification-template.md
└── qa/
    ├── source-map.md
    ├── regression-records.md
    ├── quality-gate.md
    └── scoring-rubric.md
```

## 5. Skill Entry：编写 SKILL.md

入口文件必须解决 4 件事：

1. 什么时候触发；
2. 什么时候不触发；
3. 读取哪些知识文件；
4. 输出怎样的旅行建议。

Description 必须包含典型表达和排除场景，不能只写“帮助旅行规划”。

## 6. Examples：生成完整样例

至少 3 个样例：

- 一日轻松线；
- 亲子两天一晚；
- 拍照/社媒式攻略。

每个样例包含：适用人群、前置假设、路线、节奏、预算、核验提醒、降级方案。

## 7. Regression：生成模拟回归

至少 5 条，覆盖入口、时长、人群、预算、实时核验。必须标注“模拟回归，不冒充线上日志”。

## 8. Gate：上传前门禁

检查：YAML、路径、隐藏文件、嵌套 ZIP、不支持文件、本机路径、历史占位符、PRD 落地、内容厚度。

## 9. Report：交付报告

报告必须区分：

- 结构合规完成；
- 专业能力完成；
- 仍需人工或上线后补充的事项。
