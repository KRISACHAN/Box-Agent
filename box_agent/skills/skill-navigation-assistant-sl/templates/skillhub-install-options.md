# SkillHub 安装确认模板

## 候选技能

- 名称：{{skill_name}}
- 来源：{{source_url}}
- 解决的问题：{{capability}}
- 证据状态：{{evidence_status}}

## 安装前检查

- [ ] ZIP 根目录包含 SKILL.md
- [ ] YAML front matter 可解析
- [ ] description、触发词、边界说明清楚
- [ ] 无 .DS_Store、.gitignore、LICENSE、日志、上传态隐藏文件
- [ ] 用户已确认安装或覆盖

## 确认话术

```text
我可以继续帮你安装这个技能，但这会写入本地技能目录。
请确认：是否安装 {{skill_name}}？
```

## 安装后启动

```text
/{{skill_name}}
```

如果启动失败，先检查入口名称、SKILL.md 和 YAML。