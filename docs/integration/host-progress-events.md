# Host progress event integration

Box-Agent emits agent text, tool calls, and structured tool progress through ACP session updates. Host UIs should treat `rawOutput.type` as the discriminator for structured execution state. Do not infer sub-agent state from generic fields such as `rawInput.task`; tools like `todo_write` also have a `task` argument.

## Rendering model

Recommended host layout:

- Main conversation: assistant text, final answer, and user-visible fatal errors.
- Tool/activity cards: tool calls, sub-agent progress, plan snapshots, todo snapshots, artifacts, and web search metadata.
- Default collapsed details: sub-agent internals should be grouped and collapsible, not appended one-by-one as chat messages.

## Sub-agent progress

A genuine sub-agent progress update arrives as a tool-call update whose `rawOutput.type` is `sub_agent_progress`.

Example:

```json
{
  "type": "sub_agent_progress",
  "parent_tool_call_id": "call_abc",
  "sub_agent_id": "subagent-...",
  "task_preview": "Inspect one file",
  "event": "tool_start",
  "tool_name": "read"
}
```

Grouping key:

1. Group all updates under `parent_tool_call_id` inside the parent `sub_agent` tool card.
2. Inside that card, group child rows by `sub_agent_id`.
3. Use `task_preview` only as a display label, not as an identifier.

Known `event` values:

- `step_start`: includes `step`, `max_steps`.
- `tool_start`: includes `tool_name`.
- `tool_result`: includes `tool_name`, `success`.
- `artifact`: includes artifact metadata such as `filename`, `path`, `mime_type`, `size_bytes`.
- `error`: includes `message`.
- Other values may appear for forward compatibility; render them as low-priority detail rows.

Final sub-agent summaries still arrive on the parent tool-call result (`tool_name = sub_agent`). Hosts may show the summary in the tool card, while the main conversation should wait for the parent agent's assistant message.

Strict capability-based delegation also adds a final diagnostic payload to the
parent result:

- Success: `rawOutput.type === "sub_agent_delegation"` with strategy,
  requested/resolved tools and Skills, denied optional tools, constraints,
  budgets, usage, and call counts.
- Validation/prefetch/timeout failure:
  `rawOutput.type === "sub_agent_delegation_error"` with a stable `code`,
  `message`, and `retryable` flag.

These are final-result diagnostics, not nested progress events. Render them in
the parent `sub_agent` card and keep `sub_agent_progress` as the only
discriminator for live child activity. The complete runtime contract and error
codes are documented in [Sub-agent Delegation](../SUB_AGENT_DELEGATION.md).

## Plan snapshots

Plan tools emit a structured, user-visible plan through tool-call result `rawOutput`. This is the proposed approach for the task, not execution progress.

When the user explicitly asks to plan first, Box-Agent may emit an early skeleton before the model finishes the full `plan_write` call:

```json
{
  "type": "plan_snapshot",
  "version": 1,
  "action": "start",
  "plan": {
    "id": "pending",
    "title": "正在制定执行方案",
    "objective": "根据当前请求梳理目标、范围、步骤、验证方式和风险。",
    "scope": "",
    "status": "draft",
    "steps": [],
    "verification": [],
    "risks": [],
    "assumptions": [],
    "created_at": "...",
    "updated_at": "..."
  },
  "summary": {
    "steps": 0,
    "verification": 0,
    "risks": 0,
    "assumptions": 0
  }
}
```

Hosts can force this plan flow deterministically without relying on user text heuristics by passing `_meta.forcePlanStart: true` (or `_meta.force_plan_start: true`) on `session/prompt`. The same flag can be set on `session/new` as a session default. Box-Agent emits the early `action: "start"` skeleton before the LLM call and injects hidden guidance requiring the model to publish the full plan through `plan_write`; if the model answers without a plan first, Box-Agent gives it one hidden retry before ending the turn.

The full plan later replaces the skeleton with `action: "set"`:

```json
{
  "type": "plan_snapshot",
  "version": 1,
  "action": "set",
  "plan": {
    "id": "1",
    "title": "Plan host integration",
    "objective": "Render plans separately from todo progress.",
    "scope": "Box-Agent ACP payload and host rendering contract.",
    "status": "active",
    "steps": [
      {
        "id": "1",
        "title": "Add plan_snapshot handling",
        "details": "Dispatch by rawOutput.type."
      }
    ],
    "verification": ["Check rawOutput.type in tool-call updates."],
    "risks": ["Older runtimes do not emit plan_snapshot."],
    "assumptions": ["Host renders structured rawOutput payloads."],
    "created_at": "...",
    "updated_at": "..."
  },
  "summary": {
    "steps": 1,
    "verification": 1,
    "risks": 1,
    "assumptions": 1
  }
}
```

Host behavior:

- Render this as a plan/proposal panel, not as a checklist with completion state.
- Replace the current plan state with `plan` for that session or message scope.
- If `action` is `start`, render a draft/skeleton state and expect a later `set` to replace it.
- If `action` is `clear` or `plan` is `null`, remove the current plan panel.
- Treat `plan.status` as plan lifecycle (`draft`, `active`, `revised`, `complete`), not per-step progress.
- Keep todo rendering separate; `plan_snapshot.steps` do not imply pending/in-progress/completed work.

## Todo snapshots

Todo tools emit host-friendly snapshots through tool-call result `rawOutput`:

```json
{
  "type": "todo_snapshot",
  "action": "create",
  "item": {
    "id": "1",
    "task": "Plan host integration",
    "status": "pending",
    "priority": "medium",
    "created_at": "..."
  },
  "items": [
    {
      "id": "1",
      "task": "Plan host integration",
      "status": "pending",
      "priority": "medium",
      "created_at": "..."
    }
  ],
  "summary": {
    "total": 1,
    "completed": 0,
    "in_progress": 0,
    "pending": 1
  }
}
```

Host behavior:

- Render this as a checklist/task panel.
- Replace the current todo state with `items` for that session or message scope.
- Do not classify `todo_write` as sub-agent work just because `rawInput.task` exists.
- A `todo_read` result also includes `todo_snapshot`; it may omit `action` and `item`.

## Goal snapshots

Goal state can be initialized or updated by the host, and can also be updated by the model through the `goal_write` tool. Hosts should render goal state from `rawOutput.type === "goal_snapshot"` when it appears on a tool-call update.

Example:

```json
{
  "type": "goal_snapshot",
  "action": "complete",
  "goal": {
    "objective": "Finish CLI parity and documentation",
    "status": "complete",
    "createdAt": "2026-06-19T10:00:00",
    "updatedAt": "2026-06-19T10:15:00",
    "evidence": ["uv run pytest tests/ -q passed"],
    "progress": ["Added CLI goal persistence"],
    "blockedReason": null,
    "completedBy": "model"
  }
}
```

Host-to-agent control:

- On `session/new` or `session/prompt`, pass `_meta.goal` as either a string objective or an object. Object shape supports `action`, `objective`, `status`, `evidence`, `progress`, `blockedReason`, and `completedBy`.
- At runtime, call `extMethod("goal", { sessionId, action, ... })`. Supported actions are `get`, `set`, `pause`, `resume`, `complete`, `clear`, `progress`, and `block`.
- `action: "complete"` may include `evidence` and `completedBy`; model-driven completion through `goal_write` requires non-empty `evidence`.
- `action: "block"` requires `blockedReason`.

Host behavior:

- Treat `goal.status` as one of `active`, `paused`, `blocked`, or `complete`; unknown future values should render as neutral text.
- Render `evidence` separately from `progress`. Evidence is what justifies completion; progress is a running work log.
- Store the full `goal` object if the host wants goal state to survive ACP process restarts. Box-Agent restores host-provided goal metadata but does not own host persistence.
- No new host event is required for goal autopilot. When a prompt ends naturally while the goal is still `active`, Box-Agent may continue internally in the same ACP prompt until the goal becomes `complete`, becomes `blocked`, the user cancels, the configured autopilot budget is exhausted, or repeated automatic continuations make no recorded goal progress.
- `PromptResponse.field_meta.goalAutopilot` summarizes this behavior with `enabled`, `continuations`, `budgetExhausted`, `noProgressExhausted`, `noProgressTurns`, and `lastStopReason`. If `budgetExhausted` or `noProgressExhausted` is true and the goal remains active, the ACP stop reason is `max_turn_requests`.

## Minimal TypeScript handling

```ts
function handleToolUpdate(update: ToolCallUpdate) {
  const raw = update.rawOutput;

  if (raw && typeof raw === 'object' && raw.type === 'sub_agent_progress') {
    upsertSubAgentProgress({
      parentToolCallId: raw.parent_tool_call_id ?? update.toolCallId,
      subAgentId: raw.sub_agent_id,
      taskPreview: raw.task_preview,
      event: raw,
    });
    return;
  }

  if (raw && typeof raw === 'object' && raw.type === 'plan_snapshot') {
    replacePlanSnapshot(raw.plan, raw.summary);
    return;
  }

  if (raw && typeof raw === 'object' && raw.type === 'todo_snapshot') {
    replaceTodoSnapshot(raw.items, raw.summary);
    return;
  }

  if (raw && typeof raw === 'object' && raw.type === 'goal_snapshot') {
    replaceGoalSnapshot(raw.goal);
    return;
  }

  renderGenericToolUpdate(update);
}
```

## Compatibility notes

- Older runtimes may emit `sub_agent_progress` without `sub_agent_id`; hosts can fall back to `parent_tool_call_id + task_preview` with lower confidence.
- Older runtimes may return no `sub_agent_delegation` diagnostic; keep the generic parent tool-result renderer as fallback.
- Older runtimes may not emit `plan_snapshot`; hosts should keep rendering ordinary assistant text and generic tool details as fallback.
- Older runtimes may return todo results as plain text only; hosts should keep the generic tool renderer as fallback.
- Older runtimes may emit `goal_snapshot.goal` with only `objective`, `status`, `createdAt`, and `updatedAt`; treat missing `evidence`, `progress`, `blockedReason`, and `completedBy` as empty/unknown.
- `rawOutput.type` is the stable discriminator. Avoid title/text heuristics such as `title.includes("sub_agent")` or `rawInput.task`.
