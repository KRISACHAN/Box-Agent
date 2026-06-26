# 提示词组装规范 v1.2

## 组装顺序

1. 图像类型与比例：明确海报比例、生成模式、输出用途。
2. IP 描述：只描述用户自有 IP / 原创角色，不加入真实球星肖像特征。
3. 安全隐喻：从 `hero-metaphor-map.yaml` 选取 1 个方向，并按组合识别规则裁剪线索。
4. 模板结构：从 `poster-templates.yaml` 选择模板。
5. 文案布局：优先生成无字版；如用户要求带字，也不得加入真实姓名、官方赛事名、俱乐部名、品牌名。
6. 合规限制：写入 no real person likeness、no official logos、no official jersey replication 等硬约束。
7. Negative prompt：覆盖真人脸、真实姓名、官方标识、品牌 Logo、乱码、水印、额外肢体等。

## risky_inputs 硬规则

`risky_inputs` 只用于内部识别和分类，禁止进入以下位置：

- 最终 prompt
- negative prompt 以外的可见文字
- 海报标题 / 副标题 / body
- 文件名
- alt text
- metadata
- 发布 caption

## 商业安全 prompt 句式

```text
Create a poster featuring the provided original IP mascot as a fictional football hero. Do not depict any real football player, real human celebrity, official federation, club, event, sponsor, or sportswear logo. Use only abstract football-spirit symbols and original kit design.
```

## 无字版优先规则

发布级物料默认先生成 textless key visual：

```text
No typography, no letters, no numbers as readable text, leave clean title-safe space for later deterministic text overlay.
```

如数字是隐喻元素，应优先作为抽象图形或可后期叠加文字层处理。

## 球衣原创化 prompt 规则

如果使用强关联配色，prompt 必须加入：

```text
original non-official football kit, changed color-block proportions, custom number typography, no crest, no sponsor area, no official stripe layout, no brand marks
```

## 高风险输入改写示例

用户说“像梅西”：

- 不输出：梅西、Messi、真人脸、阿根廷队徽、世界杯、迈阿密/巴萨等俱乐部符号。
- 安全输出：原创 IP 的冷静中场大师气质；最多保留“大师气质、节奏掌控、关键时刻”中的 2–3 个抽象线索，避免颜色、号码、年龄、惯用脚和具体战绩同时出现。
