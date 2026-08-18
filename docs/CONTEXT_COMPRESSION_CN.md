# 上下文压缩

Box-Agent 在两个边界控制上下文增长：

1. 工具结果在占满后续模型请求之前按需落盘；
2. 只有下一次请求接近模型有效输入上限时，才压缩会话历史。

两者彼此独立。工具结果落盘是无损的：完整结果保存在磁盘，模型只看到预览；会话摘要是有损的，因此更晚触发，并显式保留一个有界的工作集。

## 请求生命周期

```text
工具执行完成
  -> 检查单个结果
  -> 追加 tool messages
  -> 下一次 LLM 请求前检查 fresh 结果总预算
  -> 估算下一次请求大小
  -> 达到阈值才压缩历史
  -> 调用 LLM
```

## 超长工具结果落盘

`box_agent/tool_result_storage.py` 中的 `ToolResultStorage` 统一负责持久化、预览生成和会话内去重。共享执行循环同时用于串行和并行工具；CLI 与 ACP 不复制这套策略。

### 单结果即时检查

默认模型可见结果上限为 20,000 字符。工具可以声明 `max_result_size_chars`，实际使用声明值与默认值中较小者。只有尚未处理的普通结果进入这条通用策略。

以下结果不会再做二次压缩：

- 已实际采用工具 `model_context` 的结果会按 `tool_use_id` 冻结；
- `read_file`、`query_jsonl`、`search_files` 通过 Infinity 明确退出，它们分别依赖行/字符分页、cursor/结构化摘要、结果数/字符分页；
- `bash`、`bash_output` 也通过 Infinity 退出，因为工具内部已经执行一次 50,000 字符的 40% head + 60% tail 截断。

读取类工具不外置，是为了避免把读取结果写入文件后模型再次发起读取。Infinity 的含义只是退出通用压缩；工具仍可通过 `ToolResult.persistence_content` 请求统一落盘完整内容。

符合条件且超过上限时：

- 字符串保存为 `.txt`；
- 只含 text block 的数组格式化序列化后保存为 `.json`；
- 文件路径为 `~/.box-agent/sessions/<session>/tool-results/<tool_use_id>.<ext>`；
- 使用独占创建模式 `x`（等价于 `wx`），已有文件不会被覆盖；
- 模型侧结果替换为稳定的 `<persisted-output>` 预览。

以下情况保留原结果：未超过阈值、包含图片或任何非 text block、持久化失败。空输出规范化为 `(<工具名> completed with no output)`，Bash 对应 `(Bash completed with no output)`。

每个 `tool_use_id` 只做一次决策。成功落盘后的替换文本会被缓存，后续循环直接复用，不会重复写文件。恢复会话时已经存在的结果会被冻结，不会被追溯外置。

工具仍可自行保留有界输出；此时通过 `ToolResult.persistence_content` 把完整可落盘文本交给统一边界，真正的写入仍只由 `ToolResultStorage` 完成。Bash 的成功和失败命令都使用这条路径：完整输出保存到磁盘，模型继续看到工具已经生成的 head/tail，并额外得到完整输出路径，不会再被替换成通用的 2,000 字符 head 预览。工具提供的语义化 `model_context` 属于另一层职责，一旦采用也不会被即时检查或 fresh 总预算重复处理。

### 预览策略

1. 最多取前 2,000 个字符；
2. 若该窗口后半段存在换行，优先在最后一个换行处截断；
3. 否则直接截在第 2,000 个字符；
4. 只有后面仍有内容时才添加 `...`。

对尚未处理的普通结果，模型看到的形式为：

```text
<persisted-output>
Output too large (...). Full output saved to: ...

Preview (first 2.0KB):
...
</persisted-output>
```

对提供 `persistence_content` 的自截断工具，标签内改为 `Tool-bounded output`，内容是工具已经生成的有界结果，而不是再次生成的通用预览。

### fresh 结果总预算

每次 LLM 请求前，对本会话首次出现的工具结果执行默认 50,000 字符总预算检查：

1. 只处理 fresh `tool_use_id`；
2. 排除已经采用 `model_context` 的结果和声明为 Infinity 的自处理工具；
3. 按可落盘结果大小从大到小排序；
4. 总预算路径使用只含恢复路径的包装，并按包装后的模型侧实际长度记账；
5. 依次持久化并替换最大结果，直到实际剩余 fresh 内容不超过预算。

不支持的 block 和落盘失败结果保持不变。检查时 ID 会被标记为已见，因此后续请求不会反复处理。这条路径专门覆盖并行工具调用：单个结果都没有超限，但合计内容过大。

## 上下文限制压缩

### 触发阈值

```text
autoCompactThreshold = 0.9 * (context_window - max_output_tokens)
```

`LLMConfig.context_token_limit` 会先预留配置的最大输出预算，再从剩余输入预算中保留 10% 作为 token 估算误差和摘要请求的余量。

### 估算下一次请求

Provider 会把真实 API 响应的 usage 附在对应 assistant message 上。压缩器找到最近一条带真实 usage 的响应，按以下方式得到当时完整上下文：

```text
input_tokens
+ cache_creation_input_tokens
+ cache_read_input_tokens
+ output_tokens
```

然后对这条响应之后新增的消息做保守估算。若没有真实 API usage，则对整个待发送请求（包括工具 schema）取 `字符数 / 4` 与 UTF-8 字节数 `/ 3` 中较大者，避免中文及其他多字节文本被严重低估。

### 压缩后的消息组织

压缩时只调用一次摘要模型：在原始 message 列表末尾临时追加一条 `user` 摘要指令。历史不会被序列化进新 prompt，也不会分块或滚动摘要，因此摘要请求保留完整的 provider message 前缀，可以复用 KV cache。这次调用不提供工具并关闭 thinking。指令要求按时间顺序列出全部 user message，把所有结构化分析放进唯一的 `<summary>...</summary>` 块，并内置九节输出结构示例。响应必须严格由一个非空 summary 块组成；写入 `Summary:` 后只取标签内部文本，标签本身会被丢弃。正常摘要路径不设置应用层字数、token 或字符限制，但仍受 provider 输出上限约束。摘要调用失败、格式错误或返回空内容时，使用明确标注为有损的确定性有界摘要兜底。

模型输出包装成以下合成 `user` message：

```text
This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

Summary:
<模型生成的摘要>

Continue the conversation from where it left off without asking the user any further questions. Resume directly — do not acknowledge the summary, do not recap what was happening, do not preface with "I'll continue" or similar. Pick up the last task as if the break never happened.
```

新历史顺序如下：

```text
system message
摘要 user message
按规则保留的近期 messages
运行状态 user message
```

recent 选择统一覆盖 user、assistant 和 tool message；assistant 工具调用与连续 tool results 按组保留。上限为 5 条消息、合计 20,000 字符。位于 recent 后缀内的 user message 原样保留，更早的 user message 不再复制到重建历史。这里不再设置第二个“单条 tool result”上限：近期结果直接复用通用 result processor 已经处理过的模型侧内容。即使最新完整协议组本身超过数量或字符上限，也至少完整保留这一组；若重建后仍放不下，由最终估算明确标记为 blocked。

上下文压缩不再发现、重新读取或重放近期文件。

Goal、Todo 和 Plan 通过显式、无副作用的 `compaction_state` 契约读取；压缩不会执行普通工具调用。完整 active skill 指令继续固定在 system message 中，不再通过回放历史 `get_skill` 调用重建。控制策略查询“最新用户文本”时会排除内部摘要与运行状态消息。

若重建后的请求仍超过安全阈值，结果会标记为 blocked，不会静默发送一个已知超限的请求。

## 相邻保护

write/edit 工具调用参数会保留原文，直到整段历史压缩摘要其所在轮次；当前实现不会再单独将这些参数替换成历史占位符。它与工具结果落盘是两套独立机制。旧会话或外部历史中的遗留占位符仍会被安全保护拦截，不能作为可执行文件或代码参数使用。

## 验证

- `tests/test_tool_result_storage.py`：类型处理、独占写入、预览、Read 豁免、失败保留、去重和总预算排序；
- `tests/test_core.py`：请求前执行、usage 加增量估算、原始前缀单次摘要、回退估算、近期消息边界与运行状态恢复；
- `tests/test_auth.py`：阈值推导。
