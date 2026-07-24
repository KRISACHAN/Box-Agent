# 产物污染与隐私泄露检查

本检查用于城市旅行 Skill 上架前，防止开发态、运行态或本机环境信息进入最终 ZIP。

## P0 必检项

- ZIP 根层必须直接包含 `SKILL.md`。
- 不允许嵌套 ZIP。
- 不允许隐藏文件、云同步上传态文件或系统缓存文件进入包。
- 不允许 `.gitignore`、独立授权文件、日志、运行态临时文件进入上传包。
- 不允许 Word、Excel、PDF、图片等平台不支持文件进入主包。
- 不允许出现本机绝对路径、用户名、云盘目录或内部资料目录。
- 不允许出现工具历史摘要占位文本；检查时应组合识别“Full + tool-call/file/tool output + omitted + model history”等片段，不要在发布材料中直接写入完整占位串。

## 白名单打包原则

只允许以下内容进入主 ZIP：

```text
SKILL.md
README.md
package.json
CHANGELOG.md
knowledge/
references/
research/
playbooks/
templates/
examples/
qa/
scripts/
```

任何不在白名单内的文件，都不得因为“看起来无害”而被带入 ZIP。

## 人工复核口径

- 若扫描命中验证脚本自身，需要确认脚本是否把敏感词拆分生成，避免误报。
- 若命中 source map，需要确认是否暴露真实本机路径；资料来源应写成“官方文旅入口”“世界遗产官网”等通用表述。
- 若命中回归记录，需要确认是否误称模拟用例为真实线上日志。

## 通过标准

- `validate_package.py <skill-dir>` 返回 PASS。
- `validate_package.py <zip>` 返回 PASS。
- 手工抽查 ZIP 文件列表无异常。
- output 交付物只有 ZIP 与必要 Markdown 报告，不混入开发态文件。
