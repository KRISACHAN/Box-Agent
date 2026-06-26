# 错误码与异常处理指南

本指南用于让用户在配置错误、图片格式异常或字体缺失时快速定位问题。

## 错误输出格式

推荐统一格式：

```text
错误码：ERR_CONFIG_VALUE_RANGE
问题位置：examples/text-overlay-config-example.json -> text_layers[0].font_size
原因：font_size=280 超出允许范围 12-220
建议：请将 font_size 调整到 12 到 220 之间
```

## 错误码列表

| 错误码 | 场景 | 修复建议 |
|---|---|---|
| ERR_FILE_NOT_FOUND | 输入图片或配置文件不存在 | 检查路径是否正确，优先使用相对路径或绝对路径 |
| ERR_CONFIG_JSON_INVALID | JSON 无法解析 | 检查逗号、引号、括号是否完整 |
| ERR_CONFIG_FIELD_MISSING | 缺少必填字段 | 根据提示补充字段，如 `text_layers`、`text`、`font_size` |
| ERR_CONFIG_VALUE_RANGE | 参数超出范围 | 查看 `config-parameter-reference.md` 调整数值 |
| ERR_CONFIG_VALUE_TYPE | 参数类型错误 | 字号、坐标、透明度等字段需使用正确类型 |
| ERR_IMAGE_FORMAT_UNSUPPORTED | 图片格式不支持 | 使用 PNG、JPG、JPEG、WEBP |
| ERR_IMAGE_OPEN_FAILED | 图片无法读取 | 重新导出图片或检查文件是否损坏 |
| ERR_IMAGE_MODE_UNSUPPORTED | 图片色彩模式异常 | 脚本会尝试转换 RGB；失败时请手动另存为 PNG/JPG |
| ERR_FONT_NOT_FOUND | 指定字体不存在 | 配置 `font_fallback` 或改用系统字体 |
| WARN_FONT_FALLBACK | 使用了替代字体 | 检查最终文字效果是否符合预期 |
| ERR_OUTPUT_PATH_INVALID | 输出路径不可写 | 更换输出目录或检查权限 |
| ERR_COMPLIANCE_RISK_HIGH | 合规风险过高 | 减少真实人物、号码、年龄、战绩、官方标识等强线索 |

## 推荐排查顺序

1. 文件是否存在。
2. JSON 是否能解析。
3. 必填字段是否齐全。
4. 参数是否在范围内。
5. 图片格式是否支持。
6. 字体是否存在或有 fallback。
7. 输出路径是否可写。
8. 合规风险是否过高。