---
name: "storymap-generate-person"
description: "使用 1+5 Agent 协同（Supervisor + Search / Map / Editor / Critic / Deliver）为任意历史人物生成含时间线、地点、教材知识点的 Markdown 档案，并可渲染为 OSM 底图的 HTML 页面。宿主 Agent 用自身的 LLM 能力扮演 6 个角色，无需配置额外 LLM Key。地图默认优先使用国内可访问的高德公开瓦片底图，并保留 OSM 作为备用；坐标数据仍以 WGS84 为准，若使用高德底图，显示坐标需转换为 GCJ-02。触发条件：用户提到\"生成人物档案\"、\"新建历史人物\"、\"1+5 Agent\"、\"故事地图人物\"、\"add historical figure\" 等。"
---

# 故事地图 · 1+5 Agent 人物档案生成（Prompt-driven Skill）

**你**（宿主 Agent）将扮演 1 位 Supervisor + 5 位专业 Agent（SearchAgent / MapAgent / EditorAgent / CriticAgent / DeliverAgent），协同为用户指定的历史人物产出一份结构化 Markdown 档案，并可选地渲染为 Leaflet 交互地图 HTML 页面；默认优先使用国内可访问的高德公开瓦片底图，并保留 OSM 备用。

> 本 skill 不依赖任何外部 LLM Key。你直接用自己的推理能力担任 6 个 Agent 角色。

---

## 何时使用

- 用户说"生成 XXX 的人物档案"、"给 storymap 加一个人"、"用 1+5 Agent 做张仲景"
- 用户提供人物姓名并要求产出 md、html 或 storymap 页面
- 用户想批量补齐 people_master.json 中缺失的人物

## 执行流程（六步走）

按顺序完成以下 6 个阶段，每完成一步在对话里简短汇报（例如"[SearchAgent] ✓ 采集完成，得到 4 个关键时期"）。

### Step 1 · Supervisor：意图澄清

1. 从用户输入中提取**人物姓名**（必填）
2. 询问并确认（若用户未明说）：
   - 输出 md 路径（默认 `storymap/examples/story/<name>.md`）
   - 是否需要立即渲染 HTML（默认否）
   - 地理编码方式：`auto` / `osm` / `amap`（需 AMAP_KEY）；地图底图方式：`auto`（默认，国内优先高德公开瓦片，OSM 备用）/ `amap` / `osm`
3. 校验：人物是否早于 1945 年出生（storymap 项目约定）；若是现代人物请提醒用户
4. 记录一条 `execution_trace`

### Step 2 · SearchAgent：人物研究

用你的推理能力生成该人物的关键信息（不要调用外部 API）：

- **朝代 / 时期**：如"东汉末年"、"北宋"、"民国"
- **生卒年**：具体或"约 XXX 年"
- **short_review**：一句话概括其历史地位（≤ 40 字，避免"著名的"、"伟大的"这类空词）
- **关键时期**：把一生切成 4–8 个足迹节点，每个节点提供 `(年份, 古地名, 现代地名, 一句事件)`
- **代表事件与作品**：3–8 条史实性事件
- **教材知识点**：如出现在人教版语文/历史教材中，列出章节

**质量红线**：
- 拒绝生成史实存疑或明显编造的细节，宁可留白也不虚构
- 出生地存疑时用"约"或"一说 XX、一说 YY"
- 不写"李白，字太白，号青莲居士…"这类字典式简介到具体事件的 tooltip 里

### Step 3 · MapAgent：古今地名 + 坐标解析

对 SearchAgent 得到的每个地点：

1. **古今映射**：给出古地名对应的现代地名（如"沛国谯县"→"安徽亳州"）
2. **坐标获取**：按 provider 决定：
   - `provider=osm`（默认）：调用工具函数 `nominatim_lookup(现代地名)` 或从内置词典 `tools/build/data/city_coords.json` 查找
   - `provider=amap`：使用高德地理编码 API（需用户提供 `AMAP_KEY`）
3. **无法定位**的记录列入 `hard_place_queue`，md 里坐标留空但保留地名

**输出格式**：
```json
[
  {"ancient": "沛国谯县", "modern": "亳州", "lat": 33.8712, "lon": 115.7826, "confidence": "high"},
  {"ancient": "许昌", "modern": "许昌", "lat": 34.0356, "lon": 113.8261, "confidence": "high"}
]
```

**红线**：
- 坐标必须是 WGS84 十进制度（不是分秒）
- 中国境内：纬度 3–54，经度 73–135；越界视作可疑
- 严禁把 `[lat,lng]` 字符串塞到"位置"字段（历史 bug）
- 严禁产出含 U+FFFD 替换字符的地名条目，直接跳过

### Step 4 · EditorAgent：组装 Markdown

按 [MD_SCHEMA](#附录-md-schema) 严格组装。**重点**：

- 章节编号必须连续（一、二、三、四…），不重复不跳跃
- "生平时间线"用 4 列表格：`年份 | 古称 | 现称 | 事件`
- "地点坐标（自动地理编码）"用 5 列表格：`现称 | 现代搜索地名 | 纬度 | 经度 | 坐标系`
- short_review 单独占一行 `**short_review**：...`
- 表格行数与坐标条数保持一致
- 全篇简体中文，不写 emoji

### Step 5 · CriticAgent：质量守门

逐项检查（用 `[✓]` / `[✗]` 汇报）：

| # | 检查项 | 阈值 |
|---|---|---|
| 1 | LLM 思考泄露 | 无 "The user wants me to"、"Let me think"、"我需要" 类元认知 |
| 2 | 章节编号连续 | 一二三四五六（视有几章）无重复 / 跳跃 |
| 3 | short_review 非空 | 长度 6–60 字，不含"暂无""待补充" |
| 4 | 时间线单调递增 | 年份基本按时间顺序 |
| 5 | 坐标有效性 | 每个坐标在合理范围，无 (0,0)、无 null |
| 6 | 位置章节事件密度 | 每个地点至少 1 条事件描述 |
| 7 | 无占位符 | 无"暂无""不详""待补充""XXX" |
| 8 | 无坐标泄漏 | 时间线 / 位置章节里没有 `[lat,lng]` 字符串 |

**发现问题**：把具体 issue 反馈给 EditorAgent，回到 Step 4，**最多循环 3 次**。3 次仍不 pass 就以"quality warning"标记落地，不阻断流程。

### Step 6 · DeliverAgent：落盘

1. 把最终 md 写入 `--out` 指定路径（或默认 `storymap/examples/story/<name>.md`）
2. 如用户请求 `--render`：调用 `scripts/render_osm.py --md <out> --out artifacts/story_map/<name>.html --name <name>`（生成 Leaflet 交互地图页；默认使用国内可访问的高德公开瓦片底图，保留 OSM 备用图层；坐标表保留 WGS84，使用高德底图显示时需将点位转换为 GCJ-02）
3. 汇报最终交付清单和质量摘要

---

## 附录：MD Schema

Agent 产出的 Markdown 必须严格匹配以下结构：

```markdown
## <人物姓名>

**朝代**：<朝代 / 时期>
**生卒**：<约 X 年—约 Y 年>
**short_review**：<一句话概括，6–60 字>

## 一、生平简介

<200–400 字的生平简介段落，白描史实，不加"著名的""伟大的"等修饰>

## 二、代表事件与作品

- <事件 1，一句话，含年份或阶段>
- <事件 2>
- <事件 3>
...

## 三、生平时间线

| 年份 | 古称 | 现称 | 事件 |
| --- | --- | --- | --- |
| 约 X 年 | 沛国谯县 | 亳州 | 出生 |
| 约 X 年 | ... | ... | ... |

## 四、补充说明

<可选：家世、师承、后世纪念、争议等>

## 五、后世评价

- <评价 1，可以是史学家、诗人、当代研究者的引言>
- <评价 2>

## 六、地点坐标（自动地理编码）

| 现称 | 现代搜索地名 | 纬度 | 经度 | 坐标系 |
| --- | --- | --- | --- | --- |
| 沛国谯县 | 亳州 | 33.8712 | 115.7826 | WGS84 |
| ... | ... | ... | ... | WGS84 |

## 七、教材知识点（若有）

- <人教版 X 年级课文 XXX：<对应的知识点>>
```

## 附录：地图渲染工具

Skill 目录下自带一个纯 Python 脚本，无外部依赖，把 md 渲染为 Leaflet 交互地图 HTML：

```bash
python scripts/render_osm.py \
    --md storymap/examples/story/张仲景.md \
    --out artifacts/story_map/张仲景.html \
    --name 张仲景
```

输出的 HTML：
- 头部：人物名 + short_review
- 主区：Leaflet 地图，默认加载高德公开瓦片底图，提供 OSM 备用图层
- 侧栏：时间线卡片列表，点击后地图定位到对应地点
- 坐标表：保留 WGS84 数据口径
- 页脚：标注实际底图来源、OSM 备用来源与生成来源

## 附录：可选的 script-mode（有 LLM Key 场景）

若用户配置了 `LLM_API_KEY`，可跳过 prompt 扮演，直接调用主仓库封装好的 Python 6-Agent 流水线：

```bash
python .trae/skills/storymap-generate-person/scripts/generate.py \
    --name 张仲景 --render
```

（该路径需要主仓库的 `storymap.script.runtime.legacy_agent` 模块可导入，且已配置 `LLM_API_KEY`；小浣熊 / Trae skill 场景**不需要**用这条路径。）

## 使用注意

- 每完成一步都要在对话里给用户一个简短 progress 汇报（例如"[MapAgent] 解析 5 个地点，全部落到 WGS84 坐标"）
- 若 CriticAgent 循环 3 次仍未 pass，以警告落地而非拒绝交付
- 输出 md 前用 `Read` 检查目标路径是否已存在，如存在向用户确认是否覆盖
- 渲染 HTML 后可用 `open <html_path>` 让用户浏览器打开确认视觉效果
- **绝不虚构历史细节**——宁可留白，也不生成误导性内容
