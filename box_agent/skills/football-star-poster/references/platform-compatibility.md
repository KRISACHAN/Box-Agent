# 平台兼容性说明

本说明用于降低不同运行环境下的路径、字体、图片编码和输出差异，帮助用户在 SkillHub、macOS、Windows 和 Linux 环境中稳定使用本技能包。

## 1. 推荐运行方式

优先在 SkillHub 或办公小浣熊环境中使用技能入口完成合规转译、提示词生成和叠字配置。若需要本地运行确定性叠字脚本，请使用项目内 `scripts/render_text_overlay.py`，并确保已安装 Pillow。

## 2. 平台差异

| 平台 | 常见差异 | 建议 |
|---|---|---|
| SkillHub 沙箱 | 文件路径和可写目录受限 | 使用技能包内示例路径或明确指定输出目录 |
| macOS | 中文字体多为 PingFang SC / Heiti SC | 配置首选 `PingFang SC`，并保留 fallback |
| Windows | 路径分隔符、中文字体名称不同 | 优先使用 `Microsoft YaHei`，路径建议使用英文目录 |
| Linux | 可能缺少中文字体 | 建议安装或配置 `Noto Sans CJK SC` / `Source Han Sans SC` |

## 3. 路径兼容建议

- 优先使用相对路径：如 `examples/text-overlay-config-example.json`。
- 文件名尽量避免特殊符号和过长中文路径。
- Windows 路径如需写入 JSON，请使用双反斜杠或正斜杠。
- 输出目录不可写时，请更换到当前项目下的可写目录。

## 4. 图片格式兼容

推荐输入格式：PNG、JPG、JPEG、WEBP。

不建议直接使用：HEIC、TIFF、PSD、AI、PDF、动图 GIF。

脚本会尝试将非 RGB/RGBA 图片自动转换为 RGB；如果图片无法读取，应先用常见图片工具另存为 PNG 或 JPG。

## 5. 字体兼容降级

如果指定字体不存在，脚本应按 `font_fallback` 顺序寻找可用字体。若所有指定字体都不可用，则使用 Pillow 默认字体，并输出字体降级提示。

建议在配置中写入：

```json
{
  "font_family": "PingFang SC",
  "font_fallback": ["Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS", "DejaVu Sans"],
  "on_font_missing": "fallback"
}
```

## 6. 降级策略

| 问题 | 降级策略 |
|---|---|
| 字体不存在 | 使用 fallback 字体并提示 `WARN_FONT_FALLBACK` |
| 图片色彩模式异常 | 自动转换为 RGB |
| 配置字段缺失 | 输出字段名和修复建议 |
| 参数超出范围 | 输出允许范围和当前值 |
| 输出路径不可写 | 提示更换输出目录 |

## 7. 排查顺序

1. 先运行 `scripts/validate_skill.py` 检查包完整性。
2. 再用 `render_text_overlay.py --dry-run` 检查配置、图片和字体。
3. 如仍失败，按 `references/error-code-guide.md` 中的错误码定位。
4. 平台或字体差异优先查看 `references/font-compatibility-guide.md`。