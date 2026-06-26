# 字体兼容性指南

本指南用于解决不同平台字体不可用、中文缺字、字重不一致和商业字体授权不清的问题。

## 1. 基本原则

- 商业发布前，确认所用字体具备相应授权。
- 不依赖单一平台字体，所有配置都应提供 fallback。
- 中文标题优先选择可读性强、字形稳定的字体。
- 英文或数字装饰可以使用衬线字体，但不要影响中文主标题识别。

## 2. 中文字体 fallback 建议

推荐顺序：

1. PingFang SC
2. Microsoft YaHei
3. Noto Sans CJK SC
4. Source Han Sans SC
5. SimHei
6. Arial Unicode MS
7. DejaVu Sans

## 3. 英文字体 fallback 建议

推荐顺序：

1. Didot / Bodoni 风格字体
2. Georgia
3. Times New Roman
4. DejaVu Serif

## 4. 配置字段建议

```json
{
  "font_family": "PingFang SC",
  "font_fallback": ["Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS", "DejaVu Sans"],
  "on_font_missing": "fallback"
}
```

## 5. 字体缺失时的处理

脚本应输出类似提示：

```text
WARN_FONT_FALLBACK: 未找到 PingFang SC，已尝试使用 Microsoft YaHei。
```

如果 fallback 仍不可用，会使用默认字体完成输出，但最终海报应重新检查文字可读性。

## 6. 常见问题

### 字体和示例图不一样

不同平台默认字体不同。请在配置中指定字体并提供 fallback。

### 中文变成方块

说明当前字体不包含中文字符。请改用 `Noto Sans CJK SC`、`Source Han Sans SC`、`Microsoft YaHei` 或 `PingFang SC`。

### 字体太细或太粗

可调整 `font_size`、`stroke_width`、`shadow_blur` 和 `opacity`，避免只依赖字重。

### 商业字体能不能用

技能包不提供商业字体授权。用户如使用商业字体，应自行确认授权范围。