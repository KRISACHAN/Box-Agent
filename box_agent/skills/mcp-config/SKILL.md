---
name: mcp-config
description: 管理 MCP 服务器配置（mcp.json）：查看、添加、修改、移除、启用和禁用
category: workflow
keywords:
  - mcp
  - mcp配置
  - mcp.json
  - 添加服务器
  - 删除服务器
  - configure mcp
  - add mcp server
---

# MCP 配置管理

`mcp_config` 工具只改 `mcp.json`，宿主会监听文件变更并自动调 `mcp/reconnect`
完成热更新；没有宿主时重启 box-agent 才生效。

写入路径：`~/.box-agent/config/mcp.json`（优先用户目录，开发态退到 `./box_agent/config/mcp.json`）。

## 操作

```
mcp_config(action="list")
mcp_config(action="inspect_browser")  # 只读返回浏览器模式/Profile 摘要，不暴露其他 MCP 凭据
mcp_config(action="update", name="playwright", config={"args_remove":["--headless"]}) # 有头
mcp_config(action="update", name="playwright", config={"args_add":["--headless"]})    # 无头
mcp_config(action="add", name="my-server", config={"command":"npx","args":["-y","@my/mcp-server"]})
mcp_config(action="add", name="remote", config={"url":"https://example.com/mcp","type":"streamable_http"})
mcp_config(action="enable",  name="my-server")
mcp_config(action="disable", name="my-server")
mcp_config(action="remove",  name="my-server")
```

`update` 只修改提供的字段，其他字段保持不变；还支持 `args_add`、`args_remove` 和
`remove_fields`。`add` 仍用于添加或整条替换配置。

## 注意

- 启用前先去掉 `disabled` 字段，否则 reconnect 会立刻拒。
- 内置 server 由宿主托管；需要局部调整时使用 `update`，不要用 `add/remove` 整条覆盖。
