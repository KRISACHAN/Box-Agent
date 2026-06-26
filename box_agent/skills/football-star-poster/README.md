# 足球盛会球星海报合规生成技能包 v1.2.8

本技能用于把企业 IP、品牌吉祥物或原创角色，转译成足球盛会主题的合规英雄海报。它不生成真实球星肖像，不复刻官方赛事、球队、俱乐部或品牌资产，而是通过原创角色、抽象精神线索、原创球衣和确定性叠字，帮助用户完成可发布的推广海报方案。

## 我该从哪里开始？

- 第一次使用：先看 `references/quick-start-3min.md`。
- 不知道怎么触发：看本文件的“什么时候使用”和 `SKILL.md` 的“触发方式”。
- 不知道怎么配置叠字：看 `references/config-parameter-reference.md`。
- 想看可执行配置：看 `examples/text-overlay-config-example.json`。
- 想看带解释的配置：看 `examples/text-overlay-config-commented.md`。
- 遇到报错：看 `references/error-code-guide.md`。
- 字体不对或中文乱码：看 `references/font-compatibility-guide.md`。
- 平台路径、编码或裁切问题：看 `references/platform-compatibility.md`。
- 合规拿不准：看 `references/legal-disclaimer.md` 和 `references/compliance-rules.md`。
- FAQ 常见问题：看 `references/faq.md`。

## 什么时候使用

当用户提出以下需求时，可以触发本技能：

- 想用企业 IP 做足球赛事、球迷活动、门店传播、社媒海报。
- 想借鉴某类球星精神，但不希望侵犯肖像权、姓名权或商标权益。
- 想把“号码、年龄、战绩、动作、风格”等球迷记忆，改写成更安全的视觉隐喻。
- 想生成无字主视觉，再后期叠加稳定可读的中文海报文案。

不适合使用的情况：要求生成真实球星正脸、真实队徽、官方赛事 Logo、官方球衣复刻、品牌球鞋 Logo，或要求误导观众认为存在官方授权。

## 3 分钟上手

1. **说明 IP**：角色类型、主色、品牌气质、禁止出现的元素。
2. **说明灵感**：只描述精神和情绪，例如“中场大师”“冠军射手”“逆境领袖”。不要直接写真实球星姓名。
3. **选择模板**：豪华冠军海报、战报封面、复古球星卡、电影英雄海报。
4. **生成无字主视觉**：先保证角色、构图、氛围和安全区。
5. **确定性叠字**：先做“画面内 / 画面外”文案分流，再使用 `scripts/render_text_overlay.py` 和 JSON 配置叠加中文标题。
6. **质检发布**：按 `references/visual-review-checklist.md` 检查合规、可读性、IP 一致性、平台裁切和“读者视角”。

## 用户引导模式

如果输入信息不足，先问 4 个问题：

1. IP 是什么？有没有参考图或角色描述？
2. 海报用于哪里？公众号、小红书、朋友圈、门店物料还是企业内宣？
3. 想表达哪类球星精神？只能说精神方向，不要提交真实肖像或官方素材。
4. 希望输出什么？无字图 prompt、叠字配置、完整海报文案、质检清单，还是全部都要？

如果用户提到真实球星姓名，需要自动转译为安全表达；如果线索过多，需要删除号码、年龄、惯用脚、具体战绩等强指向元素。

## 叠字脚本

基础用法：

```bash
python scripts/render_text_overlay.py --image poster-textless.png --config examples/text-overlay-config-example.json --output poster-final.png
```

只检查配置、字体和图片，不输出图片：

```bash
python scripts/render_text_overlay.py --image poster-textless.png --config examples/text-overlay-config-example.json --output poster-final.png --dry-run
```

脚本支持：

- JSON 配置解析错误提示。
- 配置字段缺失提示。
- 参数范围检查。
- PNG / JPG / JPEG / WEBP 图片格式检查。
- 非 RGB/RGBA 图片自动转换。
- 字体 fallback 与 `WARN_FONT_FALLBACK` 提示。
- 输出路径不可写提示。

## 异常处理

常见错误会以错误码输出，例如：

```text
错误码：ERR_CONFIG_VALUE_RANGE
问题位置：text_layers[0].font_size
原因：当前值 300 超出允许范围。
建议：请将 text_layers[0].font_size 设置为 12 到 220 之间。
```

完整说明见 `references/error-code-guide.md`。

## 参数范围

常用参数范围：

- `font_size`：12-220。
- `opacity`：0-1。
- `x` / `y`：0-1 小数百分比，或像素整数。
- `shadow.blur`：0-80。
- `stroke_width`：0-30。
- `safe_area.margin`：0-0.3 小数，或 0-600 像素。

完整参数表见 `references/config-parameter-reference.md`。

## 字体兼容

建议使用字体 fallback，不要依赖单一平台字体。中文推荐顺序：PingFang SC、Microsoft YaHei、Noto Sans CJK SC、Source Han Sans SC、SimHei、Arial Unicode MS、DejaVu Sans。完整说明见 `references/font-compatibility-guide.md`。

## 平台兼容

不同平台在路径、字体、图片编码和中文文件名上可能存在差异。建议优先使用相对路径、PNG/JPG/JPEG/WEBP 图片和字体 fallback。完整说明见 `references/platform-compatibility.md`。

## 标准输出

一次完整交付应包含：

- 合规风险判断：PASS / REVISE / BLOCKED。
- 安全转译结果：把高风险输入改写成原创精神线索。
- 无字主视觉 prompt：适合图像生成模型使用。
- 负面提示词：排除真人相似、官方标识、品牌 Logo 和错误文字。
- 中文叠字配置：可用于确定性后期排版。
- 文案分流表：明确哪些文字进入画面，哪些只进入 brief 或合规记录。
- 视觉质检清单：检查 IP、合规、文字、平台裁切、发布风险和读者视角。

## 文件索引

- `SKILL.md`：技能入口和执行规则。
- `references/compliance-rules.md`：合规风险分级与转译规则。
- `references/hero-metaphor-map.yaml`：内部风险识别和隐喻映射词典。
- `references/poster-templates.yaml`：海报模板库。
- `references/prompt-assembly.md`：提示词组装规范。
- `references/visual-review-checklist.md`：视觉质检清单。
- `references/quick-start-3min.md`：快速上手流程。
- `references/user-upload-policy.md`：用户上传素材限制。
- `references/platform-compatibility.md`：跨平台兼容说明。
- `references/font-compatibility-guide.md`：字体兼容说明。
- `references/error-code-guide.md`：错误码说明。
- `references/config-parameter-reference.md`：配置参数范围说明。
- `references/faq.md`：统一常见问题解答。
- `examples/text-overlay-config-example.json`：可执行叠字配置。
- `examples/text-overlay-config-commented.md`：带说明的叠字配置。
- `examples/end-to-end-demo-package.md`：完整端到端演示。
- `examples/overlay-presets/`：多平台叠字配置。
- `scripts/render_text_overlay.py`：确定性叠字脚本。
- `scripts/validate_skill.py`：质量自检脚本。

## 自检命令

```bash
python scripts/validate_skill.py
```

通过后再上传 ZIP。上传包根目录必须包含 `SKILL.md`，且不得包含 `.DS_Store`、日志、临时文件、评估报告或开发过程文件。


## v1.2.8 重要更新：版本口径统一与上图文案门禁

叠字前必须把文案分成两类：

- **画面内文案**：主标题、刊名、期号、活动信息、情绪短句、封面故事 deck。
- **画面外说明**：合规提示、风险说明、prompt、negative prompt、转译策略、发布建议、法务复核提醒、技能工作原则。

默认情况下，“无肖像、无队徽、无号码、原创 IP 视觉方案”等文字只应出现在 brief 或合规记录中，不应出现在海报画面上。只有用户明确要求在画面加入免责声明、水印或合规声明时，才可作为视觉元素处理。


### 本次版本重点修复

- 统一 `SKILL.md`、`README.md`、`package.json`、参考文档和校验脚本版本号，避免用户看到不同版本产生困惑。
- 强化 `scripts/validate_skill.py`，上传前自动检查根入口、YAML front matter、README 标题、参考清单和包内隐藏旧版本号。
- 调整示例叠字配置字段，使示例与脚本实际可执行参数保持一致。
