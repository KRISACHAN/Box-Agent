# 配置参数参考

本说明用于解释确定性叠字配置的字段含义、推荐范围和常见错误。

## 1. 顶层字段

| 字段 | 类型 | 必填 | 推荐值/范围 | 说明 |
|---|---|---:|---|---|
| `canvas_width` | number | 否 | 512-4096 | 画布宽度；缺省时使用输入图片宽度 |
| `canvas_height` | number | 否 | 512-4096 | 画布高度；缺省时使用输入图片高度 |
| `safe_area` | object | 否 | 0-0.3 | 平台安全区比例 |
| `text_layers` | array | 是 | 至少 1 层 | 文本图层列表 |
| `output_format` | string | 否 | png/jpg/jpeg/webp | 输出格式 |
| `quality` | number | 否 | 60-100 | JPG/WEBP 输出质量 |

## 2. 文本图层字段

| 字段 | 类型 | 必填 | 推荐范围 | 说明 |
|---|---|---:|---|---|
| `text` | string | 是 | 1-80 字 | 要叠加的文字 |
| `x` | number/string | 是 | px 或 0%-100% | 横向位置 |
| `y` | number/string | 是 | px 或 0%-100% | 纵向位置 |
| `font_size` | number | 是 | 12-220 | 字号 |
| `font_family` | string | 否 | 系统字体名 | 首选字体 |
| `font_fallback` | array | 否 | 字体名列表 | 字体降级顺序 |
| `align` | string | 否 | left/center/right | 水平对齐 |
| `anchor` | string | 否 | mm/lt/mt/lm/rm | Pillow 锚点 |
| `color` | string | 是 | HEX/RGB | 文字颜色 |
| `opacity` | number | 否 | 0-1 | 透明度 |
| `stroke_width` | number | 否 | 0-20 | 描边宽度 |
| `stroke_fill` | string | 否 | HEX/RGB | 描边颜色 |
| `shadow` | object | 否 | 见下表 | 阴影设置 |

## 3. 阴影字段

| 字段 | 类型 | 推荐范围 | 说明 |
|---|---|---|---|
| `offset_x` | number | -80 到 80 | 横向偏移 |
| `offset_y` | number | -80 到 80 | 纵向偏移 |
| `blur` | number | 0 到 80 | 模糊半径 |
| `color` | string | HEX/RGB | 阴影颜色 |
| `opacity` | number | 0 到 1 | 阴影透明度 |

## 4. 安全区建议

| 平台 | 推荐比例 | 说明 |
|---|---:|---|
| 公众号封面 | 0.08-0.12 | 预留标题和裁切区 |
| 小红书竖图 | 0.06-0.10 | 避免文字贴边 |
| 朋友圈海报 | 0.08-0.12 | 兼顾缩略图可读性 |
| 企业内宣 | 0.05-0.10 | 根据模板自由调整 |

## 5. 示例片段

```json
{
  "text_layers": [
    {
      "text": "新的序章",
      "x": "50%",
      "y": "12%",
      "font_size": 96,
      "font_family": "PingFang SC",
      "font_fallback": ["Microsoft YaHei", "Noto Sans CJK SC", "DejaVu Sans"],
      "align": "center",
      "color": "#F4D27A",
      "opacity": 1
    }
  ]
}
```