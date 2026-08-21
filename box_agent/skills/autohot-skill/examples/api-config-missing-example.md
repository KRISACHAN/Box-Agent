# 样例：线上配置缺失

## 场景

用户要求：生成今天 AutoHOT 实时线上日报。  
当前运行环境无法确认 `AUTOHOT_BASE_URL` 或 `COZE_PROJECT_DOMAIN_DEFAULT`，也无法访问 `https://autohot.coze.site/api/daily`。

## 正确表达

当前会话尚未打通 AutoHOT 线上日报接口，因此我不能把本次结果冒充为“今天实时线上 AutoHOT 日报”。

我可以提供两种合规选项：

1. 等你补齐 `AUTOHOT_BASE_URL` / `COZE_PROJECT_DOMAIN_DEFAULT` / 必要 token 后，再拉取实时线上数据；
2. 先使用可访问的公开来源或已验证本地链路生成降级版，并明确标注“非实时线上版”。

## 禁止表达

- “已拉取今天实时 AutoHOT 线上日报。”
- “这是官网实时数据。”
- “虽然接口不可用，但我推测今天日报如下。”

## 推荐后续配置

```bash
AUTOHOT_BASE_URL=https://autohot.coze.site
COZE_PROJECT_DOMAIN_DEFAULT=https://autohot.coze.site
```
