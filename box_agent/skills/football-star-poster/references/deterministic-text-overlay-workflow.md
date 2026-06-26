# 无字版 + 后期确定性叠字流程

图片生成模型对中文文字的稳定性有限，容易出现错字、乱码、字形扭曲或排版不可控。发布级海报建议采用“两阶段流程”：

1. 先生成无字或弱字主视觉。
2. 再用确定性排版工具叠加准确中文。

## 1. 适用场景

- 企业官号发布
- 公众号封面
- 小红书/朋友圈海报
- 线下活动物料
- 需要准确中文标题、日期、品牌落款的传播图

## 2. 阶段一：生成无字主视觉

提示词要求：

- 明确写入 `no text, no typography, no letters, clean empty title-safe space`。
- 在构图中预留标题区、正文区、品牌落款区。
- 只让模型生成 IP、场景、光影、氛围和符号，不让模型渲染正式中文。

示例：

```text
Create a premium 3:4 sports hero poster with a fictional brand mascot as a blue-white number 10 football maestro. Leave a clean empty title-safe area above the carved arch and a clean subtitle area below. No text, no letters, no logos, no watermark. Use symbolic clues: number 10 on the original non-official kit, subtle 39 engraving, three small golden football icons, two goal-trail arcs.
```

## 3. 阶段二前置：上图文案门禁

在叠字前，必须先把所有文案分成两类：

| 类型 | 是否上图 | 示例 |
| --- | --- | --- |
| 画面内文案 | 可以上图 | 主标题、刊名、期号、活动时间、读者能理解的情绪短句、封面故事 deck |
| 画面外说明 | 默认不上图 | 合规提示、转译策略、prompt、negative prompt、风险说明、发布建议、法务复核提醒、工作原则 |

门禁规则：

- 出现“合规、无肖像、无队徽、无号码、原创 IP 视觉方案、发布建议、法务复核、提示词、转译策略”等词，默认移出画面。
- 如果一句话主要是解释“为什么这样做”，而不是吸引读者“为什么要看”，默认放入 brief。
- 只有用户明确要求把免责声明、水印或合规声明写入画面时，才可上图。
- 叠字配置中的 `text_layers` 只能包含通过门禁的画面内文案。

## 4. 阶段二：确定性叠字

用设计工具、HTML/CSS、PPT、Canvas、Figma 或图像处理脚本叠加文字。推荐输出文字层配置：

```json
{
  "canvas": {"ratio": "3:4", "width": 1536, "height": 2048},
  "text_layers": [
    {
      "id": "title",
      "text": "新的序章，仍在场上",
      "x": 768,
      "y": 180,
      "max_width": 1180,
      "align": "center",
      "font_family": "Source Han Serif SC, Noto Serif CJK SC, Songti SC",
      "font_size": 86,
      "font_weight": 700,
      "color": "#D8B76A",
      "effect": "subtle gold foil emboss"
    },
    {
      "id": "subtitle",
      "text": "关键时刻，连续闪光",
      "x": 768,
      "y": 310,
      "max_width": 900,
      "align": "center",
      "font_family": "Source Han Sans SC, Noto Sans CJK SC, PingFang SC",
      "font_size": 46,
      "letter_spacing": 6,
      "color": "#B98A46"
    },
    {
      "id": "body",
      "text": "传奇感，不止于名字",
      "x": 768,
      "y": 382,
      "max_width": 1100,
      "align": "center",
      "font_family": "Source Han Sans SC, Noto Sans CJK SC, PingFang SC",
      "font_size": 34,
      "letter_spacing": 4,
      "color": "#EAD9A8"
    }
  ]
}
```

## 5. 输出建议

- `poster-textless.png`：无字主视觉，适合二次排版。
- `poster-final.png`：叠字发布版。
- `poster-copy.json`：文字层配置，便于复用和修改。
- `visual-review.md`：视觉与合规质检报告。

## 6. 验收标准

- 中文文字 100% 准确。
- 标题不被平台裁切。
- 主体 IP 不被文字遮挡。
- 无真实球星肖像、官方 Logo、赛事标识或品牌标识。
- 主视觉与文字层风格一致。
- 未把合规说明、工作原则、prompt 解释或发布建议写入画面。
- 画面内每一句文字都能通过“读者视角”解释：它是给观众看的，而不是给法务/设计师/执行者看的。
