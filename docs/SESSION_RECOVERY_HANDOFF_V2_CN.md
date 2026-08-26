# Session Log、恢复与上下文持久化 Handoff V2

> 状态：源码审核后的实现方案，首版已实现。
> 持久化格式：每个 Session 一个 append-only JSONL 文件；不使用 SQLite。
> 与 V1 的关系：本文是独立 V2，不修改 `SESSION_RECOVERY_HANDOFF_CN.md`。

## 1. 本文的事实边界

本文只包含三类内容：

1. DeepSeek Harness 源码中已经存在的机制；
2. Box-Agent 当前源码中已经存在的状态和执行位置；
3. 为把前两者接起来，Box-Agent 必须新增的最小实现。

不在本文中设计后台 subagent、durable mailbox、SQLite、Snapshot、hash chain、多 writer 合并、跨文件
事务、审计 UI、日志分段或新的 ACP 私有接口。多进程同时写同一 Session 不受支持，由单 writer
排他所有权直接拒绝。

源码基线：

- DeepSeek Harness：`b150a551b8d465e31e418e1b2eaf5e79bbb7d28e`；
- Box-Agent：`e4167a98734ec2abf466510ad94f414dc2b17113` 加当前工作区变更；
- `.understand-anything` 图谱基线为 `bb52addbae8a77a0e032a4f8f9d2c6ecedaae500`，早于当前
  Box-Agent 源码，因此只用于导航，结论以直接读取源码为准。

## 2. 审核后删除的过度设计

上一版草案中的以下内容没有足够源码依据，或不是首版持久化所必需，全部移除：

- `session/repair` Event；
- `session/activation`、持久化 generation、expected-head fencing；
- `event_id`、`prev_hash`、`event_hash` 和 hash chain；
- `turn/cancel-requested`、Turn receipt 和 exactly-once Turn 协议；
- `context/replace` Event；
- `subagent/link`、`subagent/established`、`subagent/report-sent`、`subagent/settled`；
- `inbox.jsonl` 和 Durable Mailbox；
- `snapshot.json`、索引和 sealed segment；
- 内容寻址 blob 改造；
- `_session/purge`、pending deletion 等新 ACP 接口；
- 首版不需要的 approval、interaction、workflow Session Event。

其中一些机制未来可能有价值，但不能写成 DeepSeek 或 Box-Agent 当前已经具有的能力。

## 3. DeepSeek Harness 源码确认的设计

### 3.1 一个 Session 对应一个 append-only 逻辑 JSONL 日志

DeepSeek 的 JSONL 后端为每个 Session 保存一个逻辑日志。第一条是不可变 Session Header，后续每条
是一个 Session Event。关闭压缩时是原始 `.jsonl`；默认的 `.jsonl.zstd` 只是相同逻辑记录的压缩
存储形式。

Header 的源码字段为：

```text
type = "session"
version
id
createdAt
cwd?
parentSession?
seedLength?
origin?
delegationDepth?
agentPreset?
```

Event envelope 的源码字段为：

```text
type
seq
time
data
ignorable?
surfaceOp?
sourceEventSeqs?
```

DeepSeek 的 Session Event 没有 hash chain、event ID 或持久化 writer generation。`seq` 连续递增，
`time` 不负责排序。

### 3.2 Surface 是日志投影，不是另一份历史

只有以下事件直接产生模型消息：

```text
user/message
assistant/message
tool/result
```

这些事件通过 `surfaceOp` 追加或替换 Surface。其他事件保留在日志中，但不会直接进入下一次模型
请求。进程重启后重新回放日志即可得到当前 Surface。

### 3.3 耐久检查点

DeepSeek 将 JSONL 后端与检查点策略分开。检查点策略在以下语义位置等待 Session flush：

- 模型请求真正交给 provider 之前；
- 顶层工具真正开始执行之前；
- 下一 Step 开始前，确保上一步 Assistant Message 和工具结果已经持久化。

因此，硬崩溃最多丢失尚未越过语义检查点的尾部事件；工具产生外部副作用前，其 `tool/call` 已经
进入耐久前缀。

### 3.4 Repair 的真实含义

Repair 是“加载持久日志时补齐中断尾部”的恢复过程，不是名为 `session/repair` 的 Event。

DeepSeek 的 `interruptedTurnClosers()` 扫描最后一个未闭合 Turn，并追加普通事件：

1. Assistant Message 中有 tool call，但没有对应 `tool/call`：追加错误 `tool/result`，错误码为
   `TOOL_NOT_STARTED`；
2. 已有 `tool/call`，但没有对应 `tool/result`：追加错误 `tool/result`，错误码为
   `TOOL_OUTCOME_UNKNOWN`；
3. 如果 Step 未闭合，追加 `step/end`；
4. 追加 `turn/end`，reason 为 `interrupted`。

这些补齐事件继续使用正常 Event vocabulary。它们持久化成功后，Session 才对运行时可见。

JSONL 文件自己的 torn tail 修复是另一件事：后端把不完整尾部截断到最后一个已提交字节位置，再
追加可恢复的完整事件。中间损坏不能按尾部中断处理。

### 3.5 上下文压缩

DeepSeek 的压缩日志使用：

```text
compaction/start
compaction/summary
compaction/prune        # 仅实际发生无模型裁剪时
compaction/end
```

真正改变 Surface 的不是 `context/replace` Event，而是一条带
`surfaceOp: {op: "replace", start, end}` 的 Surface Event。摘要压缩通常写入一条替换范围的
`user/message`。被替换的旧事件仍保留在 append-only 日志中，因此既能恢复压缩后的上下文，也能
审计压缩前历史。

恢复 Session 时，DeepSeek 还会追加 `session/end-seed`，标记“从磁盘加载的历史到这里结束”。如果
旧日志尾部有未配对的 `compaction/start`，但它位于最新 `session/end-seed` 之前，压缩模块把它视为
旧进程遗留的未完成尝试，不再把它当作当前压缩锁。

### 3.6 Subagent

DeepSeek 的本地 subagent 使用独立 Session。Child Header 使用 `parentSession`、`origin=subagent`、
`delegationDepth` 和可选 `seedLength` 表示 lineage；Child 自己记录普通 Turn、Message、Tool 和
Compaction Event。

Child 日志中还有 `subagent/descriptor`。当前源码中 one-shot descriptor 的持久字段只有：

```text
version
mode = "one-shot"
provider
label?
```

continuable descriptor 才额外保存恢复 composition 所需的 provider/model/persona/tool filter。
DeepSeek 没有用 `subagent/link`、`subagent/established` 或 `subagent/settled` 作为父子持久化协议。
`subagent/start`、`subagent/end` 是运行观察事件，不是 Session Log 的恢复事实。

## 4. Box-Agent 当前源码事实

### 4.1 当前可恢复性

- `Agent.messages` 是进程内模型历史；
- ACP 的 `_sessions` 是进程内 handle 映射；
- `session_continuation/v1` 只能从 Host 注入有限历史，不是完整 Session replay；
- `session_trace.py` 是 best-effort 诊断 JSONL，写入失败不会影响 Agent，因此不能作为恢复事实；
- `SummarizationEvent` 是 Host 展示事件，实际上下文替换发生在 `core.py` 对 `messages` 执行
  `clear()`/`extend()` 时；
- `workflow_checkpoint_store.py` 已经是独立持久域；
- `tool_result_storage.py` 已经负责大工具结果处理。

### 4.2 当前需要恢复的 Session 状态

首版 Session Log 只接管会影响后续模型请求的状态：

- `Agent.messages`；
- `Agent.goal`；
- `PlanStore`；
- `TodoStore`；
- active Skill 的名称、内容 hash 和加载顺序；
- 当前 Turn/Step 和工具调用配对状态；
- 已提交的上下文压缩结果。

以下内容不迁入 Session Log：

- workflow checkpoint：继续由 `workflow_checkpoint_store.py` 管理；
- Memory：继续由现有 Memory 持久域管理；
- session trace：继续只用于诊断；
- ToolResultStorage 文件：沿用现有实现；
- LLM、Tool、SkillLoader、asyncio Task/Queue 等运行时对象：重启后重新构造；
- `ProgressEvent`、`LLMActivityEvent`、`LogFileEvent` 等展示或心跳事件。

### 4.3 当前 subagent 行为

`sub_agent_tool.py` 当前创建 `subagent-<uuid>`，构造独立 messages，并直接调用
`run_agent_loop()`。它把嵌套运行事件包装为 `SubAgentEvent` 发给 Host，父 Agent 最终只接收
`ToolResult`。Child 没有独立耐久 Session。

首版只处理当前已有的同步 one-shot subagent；不引入 background 或 continuable subagent。

## 5. Box-Agent V2 最小实现

### 5.1 存储布局

```text
~/.box-agent/sessions/<safe-session-key>/
├── session.jsonl
└── .writer.lock
```

`safe-session-key` 从稳定产品 Session ID 生成，不能直接信任外部 ID 作为路径。`session.jsonl` 是
唯一 canonical Session 状态文件；`.writer.lock` 是不承载 Header、Event 或恢复状态的操作锁文件。
不创建 SQLite、Snapshot 或第二份 Session 状态文件。

### 5.2 Header

首行沿用 DeepSeek 已验证的最小结构：

```json
{"type":"session","version":1,"id":"product-session-id","createdAt":0,"cwd":"/workspace"}
```

本地 subagent 只增加源码已有 lineage 字段：

```json
{"type":"session","version":1,"id":"subagent-id","createdAt":0,"cwd":"/workspace","parentSession":"product-session-id","origin":"subagent","delegationDepth":1}
```

没有真实值的字段不写，不填占位值。Header 创建后不可修改。

### 5.3 Event envelope

沿用 DeepSeek 的直接 Event 结构，不再包一层 `record: event`：

```json
{"type":"tool/call","seq":12,"time":0,"data":{"turn":2,"step":1,"callId":"call-1","name":"bash","arguments":"{...}"}}
```

规则：

- `seq` 从 0 连续递增；
- 每行必须是 lossless JSON；
- 未识别且没有 `ignorable: true` 的 Event 导致恢复失败；
- Surface Event 才能携带 `surfaceOp` 和 `sourceEventSeqs`；
- 首版不增加 hash、event ID、generation 或 revision 字段。

### 5.4 首版 Event vocabulary

与 DeepSeek 同义、直接采用：

| Event | 用途 |
| --- | --- |
| `turn/start`、`turn/end` | Turn 边界和终态 |
| `step/start`、`step/end` | 一次模型请求及其工具周期 |
| `user/message` | 用户或运行时注入的完整模型消息 |
| `assistant/chunk` | 原始流式输出，服务完整审计 |
| `assistant/message` | 组装后的模型消息 |
| `tool/call`、`tool/result` | 工具调用及模型可见结果 |
| `request/header` | 当次实际 system prompt、tools 和模型参数 |
| `request/context` | provider/model/context window 等路由事实 |
| `session/end-seed` | 标记恢复前缀结束，隔离旧生命周期遗留的开放 bracket |
| `goal/change` | `Agent.goal` 变化 |
| `todo/write` | 完整 TodoStore，last write wins |
| `compaction/start`、`compaction/summary`、`compaction/prune`、`compaction/end` | 压缩审计 |
| `subagent/descriptor` | Child 的 one-shot 身份 |

Box-Agent 为当前已有状态新增，但 DeepSeek 没有同名通用 Event：

| Event | 为什么必须新增 |
| --- | --- |
| `plan/write` | `PlanStore` 会影响后续执行，必须能从日志恢复完整当前值 |
| `skill/change` | active Skill 会改变后续 system prompt，必须恢复名称、hash 和加载顺序 |

除这两个明确的 Box-Agent 扩展外，首版不再新增其他 Event 名称。

### 5.5 Surface replay

Surface 只处理：

```text
user/message
assistant/message
tool/result
```

普通消息使用 `surfaceOp: "append"`。压缩后的摘要或 checkpoint Message 使用 replace operation，并
通过 `sourceEventSeqs` 引用被遮蔽的 Surface Event。回放得到的 Surface 写入运行时
`Agent.messages`；`Agent.messages` 不再单独作为恢复事实。

Box-Agent 的 system message 不属于 Surface。恢复时先从当前可信配置、恢复后的 active Skill 和
现有 prompt builder 重新构造 system message，再拼接 replay 得到的 Surface。旧 `request/header`
只用于审计当时实际请求，不能恢复成当前权限或工具配置。

### 5.6 写入和 flush

Session Log Module 只需要向调用方暴露四类能力：创建或加载、append、flush、close。JSON 编码、
连续 seq、单 Session 串行写和 torn tail 处理都留在 Module 内部，Core 和 ACP 不直接写文件。

创建或加载时，Module 必须先非阻塞取得 `.writer.lock` 的操作系统排他锁，再读取、校验或修复
`session.jsonl`。同一 Session 已有 owner 时立即抛出 `SessionLogInUseError`，不等待、不合并 Event，
也不引入 generation。锁持续到 `close()`；进程退出时由操作系统释放。锁文件残留不表示 Session
仍被占用，恢复不读取它的内容。

首版写入顺序：

```text
Turn 接纳：
append turn/start + user/message

模型请求前：
append step/start + request/header/request/context
-> flush + fsync
-> 调用 provider

顶层工具执行前：
append assistant/message + tool/call
-> flush + fsync
-> tool.invoke()

下一 Step 前：
append tool/result + step/end
-> flush + fsync
-> 进入下一次模型请求

Turn 结束：
append turn/end
-> flush + fsync
-> 返回 ACP PromptResponse
```

`assistant/chunk` 可以批量 append，不要求每个 chunk 单独 fsync，但越过下一语义检查点前必须被
drain。任何检查点失败都必须阻止后续 provider 请求或工具副作用。

### 5.7 冷恢复与中断闭合

恢复流程：

```text
读取并校验 Header
-> 扫描完整 JSONL records
-> 如最后一条 record 不完整，截断到最后一个完整 record
-> 校验 seq 和必需 Event vocabulary
-> 回放 Surface、Goal、Plan、Todo、Skill 和 Turn/Step 状态
-> 对开放 Turn 生成普通 closer events
-> append + fsync closers
-> append session/end-seed，标记恢复前缀结束
-> 构造 Agent
```

closer events 与 DeepSeek 保持一致：

- 未记录开始的工具：`tool/result(error.code=TOOL_NOT_STARTED)`；
- 已记录开始但结果缺失：`tool/result(error.code=TOOL_OUTCOME_UNKNOWN)`；
- 开放 Step：`step/end`；
- 开放 Turn：`turn/end(reason.kind=interrupted)`。

这里没有 `session/repair` Event。中间 JSON 损坏、Header 不匹配、seq 不连续或未知必需 Event 必须
显式失败，不能截断成一个看似正常的新 Session。恢复不会自动重跑 outcome unknown 的工具。

### 5.8 压缩提交

当前 `core.py` 只有在 `messages.clear()`/`messages.extend(new_msgs)` 时真正切换上下文。改造后应在
该位置先持久化。模型摘要路径为：

```text
append compaction/start
-> 生成现有 CompactionOutcome
-> append compaction/summary
-> append 带 replace surfaceOp 的 user/message
-> append compaction/end
-> flush + fsync
-> 再修改 Agent.messages
```

无模型的 workflow checkpoint replacement 或现有 tool-result pruning 不伪造 summary，使用：

```text
append compaction/prune
-> 紧接着 append 带 replace surfaceOp 的 Surface Event
-> flush + fsync
-> 再修改 Agent.messages
```

压缩失败且没有 replacement 时，模型摘要路径只追加带 error 的 `compaction/end`。现有
`SummarizationEvent` 继续用于 Host 展示，不代替 Session Event。

恢复只按已经提交的 replacement 重建 Surface：

| 最后耐久位置 | 恢复结果 |
| --- | --- |
| `compaction/start` 之前 | 使用旧 Surface |
| `compaction/start` 之后、replacement 之前 | 使用旧 Surface；已完成的 summary 只保留为审计记录 |
| replacement 之后、`compaction/end` 之前 | 使用新 Surface |
| 成功 `compaction/end` 之后 | 使用新 Surface |
| 带 error 的 `compaction/end`，且没有 replacement | 使用旧 Surface |

`compaction/end` 不是 Surface 提交点；replacement Event 才是。恢复不重新调用摘要模型，也不补造
摘要或成功的 `compaction/end`。`session/end-seed` 使旧生命周期遗留的 unmatched start 不再阻止
后续新压缩。旧消息 Event 永不从 JSONL 删除。

### 5.9 Subagent 持久化

当前 one-shot subagent 改为创建独立 child `session.jsonl`，但仍调用现有 `run_agent_loop()`：

```text
Parent log:
  assistant/message
  tool/call(sub_agent)
  tool/result(meta.child_session_id = child id)

Child log:
  Header(parentSession, origin=subagent, delegationDepth)
  turn/start
  user/message
  subagent/descriptor
  ...普通模型和工具 Event...
  turn/end
```

Child descriptor 只保存当前 one-shot 恢复和审计需要的字段，不复制 continuable composition：

```json
{"version":1,"mode":"one-shot","provider":"local","label":"分析持久化设计"}
```

父日志不复制 Child 的中间 Event。父 `tool/result` 使用现有结果 metadata/raw output 保存
`child_session_id`，用于从委派结果打开 Child 日志。`SubAgentEvent` 继续只用于实时展示。

Child 中断时按普通 Session 规则闭合自己的开放 Turn；父侧如果没有 durable `tool/result`，按普通
`TOOL_OUTCOME_UNKNOWN` 处理，不从 Child 日志伪造一个成功结果，也不自动重新执行委派。

首版不实现 fork history、continuable child、后台消息、mailbox 或父子跨文件事务。

### 5.10 ACP 接入

- ACP handle 仍是进程内临时 ID，不写入日志；
- `session/new` 收到稳定 `_meta.session_id` 时，按该产品 Session ID 加载或创建日志；
- 进程重启后 Host 先重新调用 `session/new`，Box-Agent 返回新的 ACP handle；
- 已成功加载 JSONL 时不再应用 `session_continuation/v1`；
- 只有找不到 JSONL 的旧 Session 才继续使用一次 continuation 迁移；
- 不在首版增加新的 ACP response 字段、purge 方法或 Turn exactly-once 协议；
- cancel 继续使用当前协作式取消，Core 退出时由 Session Log 记录正常或 interrupted Turn 终态。

## 6. 最小代码改动范围

### 6.1 新增

| 文件 | 责任 |
| --- | --- |
| `box_agent/session_log.py` | Header/Event 校验、append、flush、load、tail repair、replay |
| `tests/test_session_log.py` | JSONL、replay、checkpoint 和中断闭合测试 |
| `tests/test_agent_session_persistence.py` | 主 Agent 检查点、状态恢复和压缩持久化测试 |

如果单文件在实现后确实过大，再在不扩大外部 Interface 的前提下拆包；本文不预先创建多个空模块。

### 6.2 修改

| 文件 | 最小改动 |
| --- | --- |
| `box_agent/core.py` | 在模型、工具和实际压缩切换处 append/flush |
| `box_agent/agent.py` | 记录 Turn/Step/Surface，并从 replay 恢复 messages、Goal 和 active Skill |
| `box_agent/acp/__init__.py` | stable product Session ID 到 Session Log 的加载/创建 |
| `box_agent/tools/plan_tool.py` | Plan 写成功后记录完整 `plan/write` |
| `box_agent/tools/todo_tool.py` | Todo 写成功后记录完整 `todo/write` |
| `box_agent/tools/sub_agent_tool.py` | 为当前 one-shot child 创建独立 Session Log |
| `tests/test_core.py` | 语义检查点、压缩 replacement、中断工具测试 |
| `tests/test_acp.py` | 重启后使用相同产品 Session ID 恢复 |
| `tests/test_sub_agent_tool.py` | Child 独立日志和父结果 child ID |

`session_trace.py`、`workflow_checkpoint_store.py`、Memory 和 ToolResultStorage 不改写为 Session Log
实现，也不承担恢复事实来源。

## 7. 实施顺序

### 阶段 A：JSONL 和主 Agent 恢复

1. 实现 Header/Event schema、连续 seq、append、flush 和 tail repair；
2. 实现 Surface 和开放 Turn replay；
3. 接入 user/assistant/tool/turn/step/request Event；
4. 在模型请求和工具执行前加 flush gate；
5. ACP 使用稳定产品 Session ID 加载；
6. 完成进程重启恢复测试。

### 阶段 B：Box-Agent 状态和压缩

1. 接入 Goal、Plan、Todo、Skill Event；
2. 把当前上下文切换改为 durable replacement 后再更新 messages；
3. 验证压缩前 Event 可审计、恢复使用压缩后 Surface；
4. 验证现有 workflow checkpoint、Memory、trace 和 ToolResultStorage 行为未被接管。

### 阶段 C：当前 one-shot subagent

1. 给 Child 创建独立日志和 lineage Header；
2. 写入最小 one-shot descriptor；
3. 父普通 tool result 保存 child Session ID；
4. 验证父、子分别回放以及中断时不自动重跑。

## 8. 必须通过的测试

### JSONL

- Header 只能是第一条；
- seq 必须连续；
- 完整 Event 全部回放；
- 不完整最后一行可截断；
- 中间损坏和未知必需 Event 显式失败；
- flush/fsync 失败时模型和工具不继续执行；
- 同一 Session 的第二个 writer 立即失败，owner 关闭或进程退出后可重新加载；
- 未取得 writer 所有权时不能执行 torn tail 截断。

### 中断恢复

- 开放 Turn 追加 `turn/end(interrupted)`；
- 开放 Step 先追加 `step/end`；
- Assistant tool call 未 dispatch 得到 `TOOL_NOT_STARTED`；
- 已 dispatch、结果未知得到 `TOOL_OUTCOME_UNKNOWN`；
- 未知副作用工具不会自动重跑。

### 压缩

- replacement 提交前崩溃恢复旧 Surface；
- replacement 提交后崩溃恢复新 Surface；
- 被替换的原 Event 仍能审计；
- tool call/result pairing 不被替换范围破坏。

### Subagent

- Parent 与 Child 使用不同 JSONL；
- Child Header 的 `parentSession` 正确；
- Child 日志包含自己的模型和工具 Event；
- 父 tool result 能定位 Child Session；
- Child 中断不导致父自动重跑委派；
- `SubAgentEvent` 丢失不影响 Child replay。

## 9. 验收标准

1. Box-Agent 进程重启后，相同产品 Session ID 能从 `session.jsonl` 恢复已提交模型上下文。
2. Goal、Plan、Todo、active Skill 和压缩后的 Surface 与崩溃前最后耐久状态一致。
3. 可以从完整 Event Log 查看压缩前消息、模型输出、工具调用和工具结果。
4. 工具副作用前的 `tool/call` 已持久化；缺失结果恢复为 outcome unknown，不盲目重跑。
5. 当前 one-shot subagent 有独立日志，父结果可以定位 Child Session。
6. 删除或关闭 `session_trace` 不影响恢复。
7. 没有引入 SQLite、Snapshot、mailbox、hash chain 或新的 ACP 私有协议。
8. 同一 Session 同时只有一个 writer；冲突不会修改或修复 `session.jsonl`。

## 10. 源码位置

DeepSeek Harness：

- `packages/core/session/src/types.ts`：Header、Event、Surface vocabulary；
- `packages/core/session/src/surface.ts`：Surface append/replace replay；
- `packages/core/session/src/repair.ts`：`interruptedTurnClosers()`；
- `packages/session/session-persistence-jsonl/src/index.ts`：JSONL append、fsync、tail repair；
- `packages/session/session-checkpoint-policy/src/index.ts`：模型/工具/Step 检查点；
- `packages/compaction/compaction/src/types.ts`：compaction Event；
- `packages/compaction/compaction-basic/src/region.ts`：replacement 提交；
- `packages/subagent/subagent/src/descriptor.ts`：descriptor；
- `packages/subagent/subagent/src/child-agent.ts`：Child lineage；
- `packages/subagent/subagent-in-process-driver/src/index.ts`：one-shot Child Session。

Box-Agent：

- `box_agent/agent.py`；
- `box_agent/core.py`；
- `box_agent/acp/__init__.py`；
- `box_agent/events.py`；
- `box_agent/tools/plan_tool.py`；
- `box_agent/tools/todo_tool.py`；
- `box_agent/tools/sub_agent_tool.py`；
- `box_agent/session_trace.py`；
- `box_agent/tool_result_storage.py`；
- `box_agent/workflow_checkpoint_store.py`。
