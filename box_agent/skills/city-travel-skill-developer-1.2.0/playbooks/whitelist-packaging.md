# 白名单打包 Playbook

## 为什么必须白名单打包

城市旅行 Skill 常放在云同步目录中。云同步可能自动生成隐藏上传态文件，直接 zip 整个目录会把隐藏文件、临时文件、旧 ZIP 或不支持文件混入上传包，导致 SkillHub 解析失败或发布风险。

## 允许进入 ZIP 的根文件

- `SKILL.md`
- `README.md`
- `package.json`
- `CHANGELOG.md`（可选）

## 允许进入 ZIP 的目录

- `knowledge/`
- `playbooks/`
- `references/`
- `research/`
- `templates/`
- `examples/`
- `qa/`
- `docs/`
- `scripts/`

## 默认排除

- 所有隐藏文件和隐藏目录。
- `.gitignore`。
- 独立 `LICENSE` 文件。
- `.zip` 嵌套包。
- `.docx`、`.xlsx`、`.xls`、`.pdf`、图片等平台可能不支持的文件。
- 日志、缓存、临时文件、上传态文件。
- 任何包含本机绝对路径、用户名、密钥、内部历史占位符的文件。

## 打包后复验

必须检查：

- ZIP 根层是否直接包含 `SKILL.md`。
- 是否无嵌套父目录。
- 是否无隐藏文件。
- 是否无嵌套 ZIP。
- 是否无不支持文件。
- 解压后运行验证脚本是否通过。

## 禁止动作

- 不要通过删除源目录文件来解决污染问题，除非用户明确授权。
- 不要把旧 release 目录整体打入新版 ZIP。
- 不要手动猜测 ZIP 内容，必须读取 ZIP 条目验证。
