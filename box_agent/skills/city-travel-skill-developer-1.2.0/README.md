# 城市旅行技能开发专家

版本：1.2.0

这是一个用于开发城市旅行类 SkillHub 技能包的元技能。它的目标不是生成一份一次性旅行攻略，而是帮助用户把某个城市的旅行规划能力沉淀为可安装、可复用、可上架预审的 Skill 包。

## 适用场景

- 为泉州、澳门、西安、洛阳、苏州、景德镇、京都等城市定制旅行规划 Skill。
- 开发世界遗产、古都、博物馆、古建、非遗、亲子研学、美食 Citywalk 等主题旅行技能。
- 优化已有城市旅行 Skill 的 source map、实时核验、回归测试、TRACE/Depth 评分和上传包结构。
- 做 SkillHub 上架前核查、白名单打包和污染扫描。

## v1.2.0 重点升级

本版本沉淀了泉州旅行规划 Skill 开发过程中的 P0/P1/P2 经验：

### P0 阻断项防护

- 强制白名单打包，避免云同步隐藏文件污染。
- 增强验证脚本，检查根入口、YAML、slug、嵌套 ZIP、隐藏文件、不支持文件、本机路径、内部历史占位符。
- 加入长文件写入防误写规则。
- 明确禁止实时库存/票价/开放时间保证、代订、博彩、医疗、签证法律建议。

### P1 上架前增强

- 默认要求证据型 source map，而不是结构型 source map。
- 默认生成 TRACE + Depth 评分报告。
- 默认生成至少 10 条模拟用户回归。
- 默认生成上架前核查报告。
- 强化官方开放、预约、交通等强实时字段的复核口径。

### P2 后续增强

- 增加不同城市类型的核心资产清单模板。
- 支持真实用户试跑记录沉淀。
- 支持无障碍、外籍游客、研学团等细分场景继续扩展。

## 推荐输出结构

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

上架候选包必须包含：

- `qa/source-map.md`
- `qa/trace-depth-scorecard.md`
- `qa/regression-records.md`
- `qa/prelaunch-review.md`
- `scripts/validate_package.py`

## 使用方式

示例请求：

```text
/city-travel-skill-developer 请给泉州定制一个专门的旅行规划 Skill，完全自动，输出到 xxx 目录。
```

```text
/city-travel-skill-developer 请优化这个城市旅行 Skill，补官方 source map、TRACE/Depth 评分、10 条回归和上架前核查。
```

## 验证方式

在技能包目录运行：

```bash
python scripts/validate_package.py <package-dir>
```

通过标准：

```text
errors=0
warnings=0
```

脚本通过不等于专业评审完全通过。正式上架前仍建议做人工体验试跑和官方入口复核。
