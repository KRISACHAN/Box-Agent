# 发布门禁

打包前逐项勾选。

## YAML / 结构

- [ ] 根目录存在 SKILL.md
- [ ] `name` = `film-tv-license-application-assistant`
- [ ] description 含能力、触发、排除；无 `<` `>`；≤1024 字
- [ ] package.json.name 一致
- [ ] SKILL.md 按需引用 references，无空壳文件

## TRACE

- [ ] Trust：C 级不升级为法律意见；数字带来源
- [ ] Reliability：七段模板；危险请求拒绝
- [ ] Adaptability：四条许可 + VR/合拍 + 微短剧
- [ ] Effectiveness：手册与官方冲突处手册让路

## Depth

- [ ] source-map 存在
- [ ] 若-则写入 faq-rules / SKILL 路由表
- [ ] phrasebook 含追问/降级/拒绝
- [ ] T1–T12 已写期望

## 安全与上传

- [ ] 无密钥、无本机用户主目录绝对路径、无真实客户名
- [ ] 无 `.DS_Store`、云盘 cfg、运行日志
- [ ] 无官方 PDF 二进制入包
- [ ] 无自动登录/申报脚本

## 运行

```bash
python3 scripts/validate_package.py .
```

然后用 skill-creator 的 `package_skill.py` 生成 `.skill`。
