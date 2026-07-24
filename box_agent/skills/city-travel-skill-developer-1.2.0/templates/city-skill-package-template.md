# 模板：城市旅行 Skill 包标准结构

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
    ├── prd-implementation-audit.md
    ├── regression-records.md
    ├── quality-gate.md
    └── scoring-rubric.md
```

## SKILL.md 最小骨架

```markdown
---
name: <english-slug>
display_name: <中文名>
description: "面向中文用户的<城市>旅行规划 Skill。当用户询问<城市>怎么玩、一日游、亲子游、拍照路线、美食安排、交通动线、避坑建议时使用；不用于机票酒店实时比价、代订、博彩或法律医疗咨询。"
version: "1.0.0"
tags:
  - travel
  - city-guide
  - itinerary
---

# <城市>旅行规划助手

## 北极星目标

...
```

## 使用说明

复制结构后，必须把示例城市、触发词、排除场景、知识文件与 QA 文件全部替换为目标城市内容。不得只改标题。
