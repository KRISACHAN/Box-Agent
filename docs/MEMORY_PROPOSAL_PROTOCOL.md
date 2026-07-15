# Memory Promotion Protocol

> 适用版本：Box-Agent ≥ 0.8.32
> 关联协议：[MEMORY_INTEGRATION.md](./MEMORY_INTEGRATION.md)、[MEMORY_MATCH_PROTOCOL.md](./MEMORY_MATCH_PROTOCOL.md)

本协议用于让 ACP 宿主在「记忆页面」上展示**「可以加入核心记忆 (MEMORY.md) 的候选条目」**，由用户逐条决定是否升级为长期记忆。

当前策略比早期版本更保守：候选只来自 v2 experience memory，不来自 legacy `CONTEXT.md`；自动匹配不会累计晋升证据；只有 user/profile/preference 类型的高信号条目才可能被提议。

## 0. 名词与背景

- **Core 记忆**：`MEMORY.md`，每次会话自动注入 system prompt。宿主已能读写。
- **Context / experience 记忆**：`v2/experiences/<topic>.md`，按需检索（`memory_search` / 自动匹配）。每条携带 `hits` / `last_used` / `confidence` 等元数据。
- **Legacy context**：旧版 `CONTEXT.md` 或 `context/<topic>.md`。只作为显式 `memory_search` 的只读兜底，不参与自动匹配、提议、迁移或重写。
- **升级 (promotion)**：把 v2 experiences 中命中频次较高且适合长期注入的条目移动到 `MEMORY.md`，成为永久注入的核心记忆。
- **候选 (candidate)**：满足以下全部条件的 Context 条目：
  - `hits >= memory_promotion_hit_threshold`（默认 5）
  - `core_status != "rejected"`（拒绝是永久的）
  - `source != "core"`（已经在核心的不算）
  - `topic` 是 `user_profile` 或 `preferences`
  - `last_proposed` 为空，或早于 `memory_promotion_cooldown_days`（默认 14 天）之前

候选筛选完全由 Agent 侧实现；宿主**只关心展示与决策回写**。

---

## 1. 三个交互通道

| 通道 | 逻辑名 | 实际 wire 方法名 | 方向 | 用途 | 实现状态 |
|---|---|---|---|---|---|
| **Push** | `session/memory_proposal` | `_session/memory_proposal` | Agent → Host | 每轮 turn 结束前主动推送候选 | ✅ 已实现 |
| **Pull** | `memory_proposal_list` | `_memory_proposal_list` | Host → Agent | 记忆页面打开时主动拉取候选 | ✅ 已实现 |
| **Apply** | `memory_proposal_apply` | `_memory_proposal_apply` | Host → Agent | 用户做完决策后回写 | ✅ 已实现 |

> 所有方法都走 ACP 的 `extMethod` 扩展通道。JSON-RPC wire 上的方法名带 `_` 前缀（路由层会剥掉前缀再分发）。**注意**：只有 Push 通道带 `session/` 段（`_session/memory_proposal`）；Pull / Apply 是裸名（`_memory_proposal_list` / `_memory_proposal_apply`，**没有** `session/` 段）。宿主务必按上表的「实际 wire 方法名」调用，否则会拿到 `unknown_method`。

### 推荐集成模式

记忆页面的体验只依赖 **Pull + Apply**：

1. 用户打开记忆页面 → 宿主调用 `memory_proposal_list`（wire `_memory_proposal_list`）→ 拿到候选数组
2. 在已展示的 core 内容下方加一个区块「待加入核心的记忆 (N)」
3. 每条候选展示 `content` + `hits` + `confidence` + 三个按钮：**加入核心 / 暂不 / 永不再提议**
4. 用户做完选择后，宿主调用 `memory_proposal_apply`（wire `_memory_proposal_apply`），附上 `{id: decision}` 映射
5. Agent 完成持久化并返回操作小结，宿主刷新页面状态

Push 通道可选作为「红点提醒」：当 Agent 推来一批新候选时，宿主在记忆入口加徽标，但不必弹出模态——用户进入页面时再用 Pull 拉到完整列表即可。

---

## 2. Push：`session/memory_proposal`（Agent → Host）

**触发时机**：每轮 turn 结束（`DoneEvent(END_TURN)` 或 `DoneEvent(MAX_STEPS)`）之前，v2 候选非空时。

**幂等性保证**：Agent 在发送前会把每条候选的 `last_proposed` 戳到当前时间，所以：

- 宿主响应「全部 skip」或干脆不响应 → 这批候选会进入冷却（默认 14 天）后才会重新出现
- 宿主返回 `method_not_found` → Agent 静默降级为 skip-all（同样不会再骚扰）

### 请求 payload

```json
{
  "sessionId": "session-uuid",
  "proposals": [
    {
      "id": "ctx_20260517_a1b2c3",
      "content": "用户偏好在 PPT outline 阶段先确认章节再展开细节",
      "hits": 7,
      "confidence": 0.85
    },
    {
      "id": "ctx_20260516_d4e5f6",
      "content": "项目使用 uv 管理依赖，禁止 pip 直装",
      "hits": 12,
      "confidence": 1.0
    }
  ]
}
```

### 响应 payload

```json
{
  "decisions": {
    "ctx_20260517_a1b2c3": "pin",
    "ctx_20260516_d4e5f6": "skip"
  }
}
```

字段约束：

- `decisions` 是 `{entry_id: decision}` 映射
- `decision` 取值：`"pin"` | `"skip"` | `"reject"`，大小写敏感
- **未出现在响应里的 id 视为 skip**
- 非 candidates 列表里的 id 会被忽略
- 不合法的 decision 字符串会被忽略

### 超时与错误

- Agent 端等待 **120 秒**。超时按 skip-all 处理。
- 宿主侧若需要异步等待用户操作（用户没立刻看到通知），**不要在 push 通道里挂 120 秒**。推荐做法：宿主立刻返回 `{decisions: {}}`（空决策），让 Agent 结束 turn；真正的决策走 Pull/Apply 通道。

---

## 3. Pull：`memory_proposal_list`（Host → Agent，wire `_memory_proposal_list`）

**用途**：记忆页面打开 / 刷新时主动拉取候选。

### 请求 payload

```json
{
  "sessionId": "session-uuid",
  "includeCooldown": false
}
```

字段：

- `sessionId`（必需）：当前会话 id
- `includeCooldown`（可选，默认 `false`）：是否包含还在冷却期内的候选
  - `false`：与 Push 通道筛选规则一致（命中阈值 + 不在冷却 + 未被永久拒绝）
  - `true`：忽略冷却限制，等同于 CLI 的 `/memory review` 行为，用于「让我手动看一眼所有可升级的」

### 响应 payload

```json
{
  "candidates": [
    {
      "id": "ctx_20260517_a1b2c3",
      "content": "用户偏好在 PPT outline 阶段先确认章节再展开细节",
      "hits": 7,
      "confidence": 0.85,
      "created": "2026-05-10T08:30:00",
      "last_used": "2026-05-17T14:20:00",
      "last_proposed": ""
    }
  ]
}
```

字段：

- `candidates` 数组，空时返回 `[]`
- 比 Push payload 多 `created` / `last_used` / `last_proposed` 三个元数据，便于宿主决定排序、显示「最近一次命中时间」等
- `last_proposed` 为空字符串表示从未推送过

> Pull 不会修改 `last_proposed` —— 它是只读查询。

---

## 4. Apply：`memory_proposal_apply`（Host → Agent，wire `_memory_proposal_apply`）

**用途**：用户在记忆页面做完选择后批量回写。

### 请求 payload

```json
{
  "sessionId": "session-uuid",
  "decisions": {
    "ctx_20260517_a1b2c3": "pin",
    "ctx_20260516_d4e5f6": "reject"
  }
}
```

`decisions` 字段语义与 Push 响应完全一致。

### 响应 payload

```json
{
  "pinned": 1,
  "rejected": 1,
  "skipped": 0,
  "core": "...完整的 MEMORY.md 新内容..."
}
```

字段：

- `pinned`：本次成功加入核心的数量
- `rejected`：本次永久拒绝的数量
- `skipped`：本次跳过的数量（含被忽略的非法 decision）
- `core`：操作后的完整 `MEMORY.md` 文本，方便记忆页面直接用它刷新「已编辑的核心区块」，避免再读一次文件

---

## 5. 各 decision 的语义与副作用

| Decision | v2 experience entry | MEMORY.md | 是否再提示 |
|---|---|---|---|
| `pin` | 删除该条 | 追加该条内容（行级去重） | 否（已不在 v2 experience 里） |
| `reject` | 保留，但 `core_status="rejected"` | 不变 | **永久不再提示**（即使将来 hits 翻倍） |
| `skip` | 不变 | 不变 | 冷却结束后 (14 天) 再次出现 |

**关键不变量**：

1. **同一条记忆永远只在一处**：pin 后只在 MEMORY.md，reject 后只在 v2 experience 里且带 rejected 标记，绝不会两边都有。
2. **MEMORY.md 行级去重**：宿主若同时通过自己的编辑功能往 MEMORY.md 写了相同的内容，Agent 在 pin 时不会再追加一遍。
3. **rejected 是终态**：即便用户后悔，目前只能通过手工编辑 v2 experience 里那条的 `core_status` 元数据来恢复（罕见，无需 UI 支持）。

---

## 6. 数据结构：`ContextEntry`

记忆页面如果想直接读 v2 experience 文件（不推荐，但可行），文件格式如下：

```
<!-- ctx id=ctx_20260517_a1b2 created=2026-05-17T08:30:00 last_used=2026-05-17T14:20:00 hits=7 source=extractor confidence=0.85 -->
用户偏好在 PPT outline 阶段先确认章节再展开细节
```

字段 `core_status=rejected` 和 `last_proposed=<ISO>` 仅在非默认值时序列化。旧版 `CONTEXT.md` 不再自动迁移；它会保留在原位，仅作为显式搜索兜底。

更推荐通过 Pull/Apply 协议交互，把文件解析的细节留给 Agent 侧。

---

## 7. 配置项

`config.yaml` 中可调（宿主一般无需暴露给终端用户，使用默认值即可）：

```yaml
memory_promotion_proposal_enabled: true   # 总开关；false 时 push 通道彻底关闭
memory_promotion_hit_threshold: 5         # v2 explicit-search hits 达到这个值才算候选
memory_promotion_cooldown_days: 14        # 冷却天数
```

宿主侧若希望「永远不推送，只通过页面 Pull 」：把 `memory_promotion_proposal_enabled` 关掉即可，Pull/Apply 通道不受这个开关影响。

---

## 8. 集成清单 (Checklist)

宿主侧实施步骤：

- [ ] 在记忆页面 mount 时调用 `memory_proposal_list`（wire `_memory_proposal_list`），渲染候选区块
- [ ] 用户点击 **加入核心 / 暂不 / 永不再提议**，按钮状态收集到 `decisions` 映射
- [ ] 用户离开页面或点击「保存」时调用 `memory_proposal_apply`（wire `_memory_proposal_apply`）一次性提交
- [ ] 收到 Apply 响应后，用返回的 `core` 字段刷新核心区块；候选区块从列表里移除被 pin / reject 的条目
- [ ] （可选）实现 `session/memory_proposal`（Push，wire `_session/memory_proposal`）接收：仅用于在记忆页面入口显示红点
  - 不打算用红点时，可以**直接返回 `{decisions: {}}`** 或不实现这个 method（Agent 端 method_not_found 已正确降级）

---

## 9. 与 CLI 的对齐

CLI 端通过 `/memory review` 命令做同样的事，等价于 `includeCooldown=true` 的 Pull + 终端 prompt 的 Apply。
ACP 端的「记忆页面」语义与 CLI 一致，确保两侧行为统一（参见 `feedback_dual_side_coverage` 项目原则）。

---

## 10. 兼容性

- 旧版 Box-Agent (< 0.8.32)：所有 `_session/memory_proposal` / `_memory_proposal_list` / `_memory_proposal_apply` 调用会返回 `method_not_found`，宿主侧应当兼容降级（不显示候选区块即可）。
- 旧版宿主 + 新版 Box-Agent：Push 通道返回 `method_not_found` 后 Agent 静默降级，不会影响 turn 正常结束。
- 新版 Box-Agent 不迁移旧 `CONTEXT.md` / `context/<topic>.md`。这些旧数据仍可被显式 `memory_search` 兜底命中，但不会再出现在候选列表。宿主已经展示过的旧候选可以直接丢弃或等下一次 Pull 以 Agent 返回为准。
