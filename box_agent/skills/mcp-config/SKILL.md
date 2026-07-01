---
name: mcp-config
description: 管理 MCP 服务器配置（mcp.json）：查看、添加、移除、启用、禁用
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
mcp_config(action="add", name="my-server", config={"command":"npx","args":["-y","@my/mcp-server"]})
mcp_config(action="add", name="remote", config={"url":"https://example.com/mcp","type":"streamable_http"})
mcp_config(action="enable",  name="my-server")
mcp_config(action="disable", name="my-server")
mcp_config(action="remove",  name="my-server")
```

`add` 接受的字段：stdio 用 `command/args/env`；URL 用 `url/type/headers`；
共有 `connect_timeout/execute_timeout/sse_read_timeout/disabled`。其他字段被静默丢弃。

## 注意

- 启用前先去掉 `disabled` 字段，否则 reconnect 会立刻拒。
- 内置 server（`playwright`、`browser-gateway`、`mcp-server-askecho-search-infinity`）由宿主托管，不要改。
