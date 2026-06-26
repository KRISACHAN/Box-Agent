# 叠字配置注释版示例

> JSON 文件本身不支持注释，所以这里用 Markdown 解释每个字段。正式运行请参考 `examples/text-overlay-config-example.json`。

## 最小配置

```json
{
  "input_image": "examples/input/poster-blank.png",
  "output_image": "examples/output/poster-with-text.png",
  "canvas": {
    "width": 1080,
    "height": 1440
  },
  "text_layers": [
    {
      "text": "新的序章",
      "x": "50%",
      "y": 120,
      "font_size": 72,
      "font_family": "PingFang SC",
      "font_fallback": ["Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS", "DejaVu Sans"],
      "color": "#F4D38A",
      "align": "center",
      "opacity": 1.0
    }
  ]
}
```

## 字段说明

- `input_image`：输入图片路径。推荐 PNG/JPG/JPEG/WEBP。
- `output_image`：输出图片路径。父目录需要可写。
- `canvas.width` / `canvas.height`：输出画布尺寸，建议 512-4096。
- `text_layers`：文字层数组，可设置多行标题、章标题、口号。
- `text`：要叠加的文字。避免真实球星姓名、官方赛事名、官方队徽和品牌标识。
- `x` / `y`：文字位置。可用像素数字，也可用百分比字符串，如 `"50%"`。
- `font_size`：字体大小，建议 12-220。
- `font_family`：首选字体。
- `font_fallback`：字体缺失时的备用字体列表。
- `color`：字体颜色，建议 HEX，如 `#FFFFFF`。
- `align`：`left`、`center`、`right`。
- `opacity`：透明度，范围 0-1。
- `stroke_width`：描边宽度，建议 0-20。
- `shadow_blur`：阴影模糊，建议 0-80。

## 检查命令

```bash
python scripts/render_text_overlay.py --config examples/text-overlay-config-example.json --dry-run
```

如果 dry-run 通过，再执行正式叠字。