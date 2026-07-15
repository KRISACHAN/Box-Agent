# Memory Match Protocol

> 适用版本：Box-Agent ≥ 0.8.38

本协议用于让 ACP 宿主展示“本轮任务中搜索/自动匹配到的 context / experience memory”。

## 1. Core memory 不返回前端

`MEMORY.md` 仍会在会话创建时注入 system prompt，供模型理解用户身份、偏好和长期规则。

但 `MEMORY.md` **不会**通过 `session/new._meta` 返回给前端，也不建议展示“我已参考这些记忆”。

原因：

- core memory 是模型长期上下文，不是本轮检索结果。
- 新建 session 时展示它对用户价值不高，且容易造成打扰。
- 前端只需要展示本轮搜索/自动匹配到的 context / experience 结果。

## 2. 显式搜索命中的上下文记忆

当模型根据 `memory_summary.md` 或当前问题判断需要查询记忆并调用 `memory_search` 时，工具结果的 `rawOutput` 会返回结构化匹配：

```json
{
  "type": "memory_search",
  "query": "weekly",
  "matched_memories": [
    {
      "id": "context:1",
      "source": "context",
      "category": "context",
      "text": "- Weekly report format: progress/issues/next week"
    }
  ]
}
```

没有命中时：

```json
{
  "type": "memory_search",
  "query": "weekly",
  "matched_memories": []
}
```

## 3. 自动匹配命中的上下文记忆

每轮 prompt 开始前，后端会对用户问题做保守关键词/短语相似匹配。自动匹配只读 v2 experiences，不读 legacy context；命中后会通过同样的 `memory_search` rawOutput 结构发给宿主，并额外带上：

```json
{
  "type": "memory_search",
  "trigger": "auto",
  "query": "科技公司入职培训 都需要注意什么",
  "matched_memories": [
    {
      "id": "context:12",
      "source": "context",
      "category": "context",
      "text": "- 会话连续性反馈：用户会以“科技公司入职培训 ppt 做好了吗”等方式追问既有交付状态。"
    }
  ]
}
```

前端可以统一识别：

```ts
if (rawOutput?.type === "memory_search") {
  renderMatchedMemories(rawOutput.matched_memories);
}
```

`trigger === "auto"` 只用于区分“后端自动匹配”与“模型显式调用 memory_search”，不是必需字段。自动匹配是弱提示，不会增加 `hits` / `last_used`，也不会成为晋升证据。

## 4. 展示边界

- `matched_memories` 为空时通常不展示。
- 文案建议使用“可能相关的记忆”，不要写成“确定参考了这些记忆”。
- 该协议只展示搜索/匹配结果；自动提取出的新记忆展示属于后续实现。
- 显式 `memory_search` 先查 v2 experiences；v2 无命中时会只读兜底查旧 `CONTEXT.md` / `context/<topic>.md`。宿主不需要为此改字段，但不要把 legacy 命中当成可晋升材料。
