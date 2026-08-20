# 第三方 API 兼容性

## 事件顺序错误

### 问题描述

某些声称兼容 Anthropic 协议的第三方 API 可能发送不符合规范的 SSE 事件顺序。例如，在发送 `message_start` 事件之前就发送了 `content_block_start` 事件。

当这种情况发生时，anthropic SDK (v0.72.1+) 会抛出错误：
```
RuntimeError: Unexpected event order, got content_block_start before "message_start"
```

### 错误示例

```json
{
  "timestamp": "2026-06-12T08:29:49.292Z",
  "level": "DEBUG",
  "event": "llm/error_meta",
  "provider": "anthropic",
  "mode": "stream",
  "error_type": "RuntimeError",
  "error": "Unexpected event order, got content_block_start before \"message_start\""
}
```

### 解决方案

从 v0.8.68 开始，Box-Agent 会捕获这类错误并提供更友好的提示：

```
API 返回的事件顺序不符合 Anthropic 协议规范: Unexpected event order, got content_block_start before "message_start"
这通常表示第三方 API 的兼容性问题。请检查:
1. API 端点是否正确实现了 Anthropic 流式协议
2. 是否应该使用 OpenAI 兼容模式（provider: openai）而不是 Anthropic 模式
```

### 推荐操作

如果遇到此错误：

1. **检查 API 配置** - 确认使用的 API 端点是否真正支持 Anthropic 协议
2. **切换到 OpenAI 模式** - 如果 API 实际上是 OpenAI 兼容的，修改配置：
   ```yaml
   llm:
     provider: openai  # 而不是 anthropic
     api_base: "your-api-endpoint"
     model: "your-model"
   ```
3. **联系 API 提供商** - 报告事件顺序问题，要求修复协议兼容性

## Anthropic vs OpenAI 协议选择

### 何时使用 `provider: anthropic`

- 官方 Anthropic API (api.anthropic.com)
- 明确声称完全兼容 Anthropic 协议的第三方 API
- 需要使用 Anthropic 特有功能（如 thinking blocks）

### 何时使用 `provider: openai`

- OpenAI 官方 API
- 大多数国内大模型 API（如 DeepSeek、SiliconFlow、智谱等）
- 使用 OpenAI 兼容格式的第三方代理

### 诊断工具

运行 `box-agent doctor` 可以测试 API 连接性和基本兼容性。

## SenseNova OpenAI 兼容模式

当 `provider: openai` 且模型名以 `sensenova-` 或 `sn-sensenova-` 开头时，
Box-Agent 会启用 SenseNova 协议兼容处理。使用 `--deep-think` 或 ACP 的
`deep_think` 开关时，请求会附带：

```json
{
  "chat_template_kwargs": {
    "thinking": true,
    "reasoning_effort": "high"
  }
}
```

部分 Flash-Lite 版本会把工具调用以 `<tool_call>` 标记输出到 reasoning，或
输出到不含其他可见文本的 content。Box-Agent 会把这类标记恢复为标准工具调用，
但仅接受当前步骤实际开放的 canonical tool name、显式 alias，以及它们的
下划线转连字符兼容形式。未声明的工具名和夹杂普通可见文本的内容不会执行，
仍作为文本返回。Provider-facing 工具 Schema 始终只包含 canonical name。
