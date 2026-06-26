# Release Notes v1.2.8

## 发布目标

本版本针对反馈“部分文件版本号没对上，可能导致使用困惑”进行专项修复，并按 SkillHub TRACE 视角补强上传前自检。

## 变更摘要

- 统一版本号：`SKILL.md`、`README.md`、`package.json`、`references/visual-review-checklist.md`、`scripts/validate_skill.py` 均统一为 `1.2.8`。
- 强化自检脚本：新增 README 标题、参考质检清单、全包旧版本号扫描、YAML 解析和 ZIP 根入口相关检查。
- 修复示例口径：为叠字示例配置补齐 `font_fallback` 与兼容字段，降低首次运行困惑。
- 保留完整原有能力：合规转译、无字图优先、确定性叠字、错误码、平台兼容、字体 fallback、用户上传限制与示例均完整保留。

## 上传前验收

```bash
python scripts/validate_skill.py
```

通过后再从包根目录打 ZIP，ZIP 根层必须直接包含 `SKILL.md`。
