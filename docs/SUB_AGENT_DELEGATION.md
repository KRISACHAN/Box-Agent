# Sub-agent Delegation

This document is the source-of-truth contract for the `sub_agent` tool. It
covers the flat public request, derived child policy, bounded batch fast path,
budgets, and host diagnostics. For UI progress rendering, also read
[Host Progress Events](integration/host-progress-events.md).

## Execution model

A child has an independent message history but reuses the parent session's
resolved LLM client and live tool instances. Existing resource-level checks,
including `PermissionEngine`, remain authoritative. The parent still owns task
selection, conflict handling, final deliverables, and final verification.
Recursive `sub_agent` calls are always rejected.

A child has no independent authority. It reuses the parent session's permission
negotiator: an out-of-scope tool request is approved by the host on behalf of
the parent session and retried once after approval. Rejection and timeout remain
fail-closed. Identical concurrent filesystem requests share one host prompt,
while distinct requests are presented serially. One-shot safety approval for
dangerous commands is never coalesced.

## Public request

The ordinary request is intentionally flat:

```json
{
  "title": "API review",
  "task": "Compare the API documents and report incompatible changes.",
  "required_tools": ["read_file"],
  "skills": ["code-review"],
  "budget": {"max_steps": 12, "max_tool_calls": 25}
}
```

All fields except `task` are optional. Unknown top-level fields fail with
`INVALID_DELEGATION_SPEC`; the caller may correct the named fields once.
The removed nested `execution`, `capabilities`, `inputs`, and `constraints`
objects are not accepted.

### Safe defaults

When `required_tools` is omitted, the child receives only the currently
available members of this trusted local-read set:

- `read_file`
- `query_jsonl`
- `search_files`

An explicit empty list creates a tool-free child. Selected Skills add guidance
only; Skill metadata cannot add tools or widen policy.

The child inherits stable parent safety and workspace constraints, but not the
parent's managed auto-loaded or on-demand Skill bodies. Child-specific Skill
guidance must be selected explicitly or supplied as task input, preventing
large parent workflows from exhausting the smaller child context before work
begins.

## Derived child policy

The runtime derives policy from explicitly selected tools instead of asking the
model to author permission booleans:

- `bash` is delegated only when explicitly selected and a parent-session
  permission negotiator is available; every delegated command requires
  one-shot parent approval;
- `execute_code` and other process tools are not delegated;
- tools with external side effects are not delegated;
- unknown MCP tools fail closed;
- known read-only network tools are enabled only when selected explicitly;
- path-based writes require an exact `write_scope`;
- Skills cannot expand the resolved tool set.

Known read-only network tools include `web_search`, `web_extract`,
`inspect_images`, and the managed Playwright navigation/inspection tools
recognized by trusted server metadata. `generate_image` is an explicitly
selected trusted network capability.
Interactive browser actions and arbitrary browser code remain external-side-
effect capabilities and are denied.

### Scoped writes

`write_file`, `append_file`, and `edit_file` require a non-empty
artifact-root-relative `write_scope`:

```json
{
  "task": "Write the verified findings to the assigned file.",
  "required_tools": ["web_search", "write_file"],
  "write_scope": ["research/dim01.md"]
}
```

The runtime wraps those tools and rejects paths outside the delegated scope
before invoking the live parent tool. Parallel children must receive disjoint
scopes. A child may pass either the artifact-root-relative path or its resolved
absolute equivalent; both are checked against the same live file-tool root. A
scope without a path-based write tool is invalid.
`write_scope` does not constrain shell semantics; explicitly delegated `bash`
commands are wrapped so every exact command requires one-shot parent approval.

## Bounded local-file batch fast path

Passing `files` supplies local task inputs to either execution path. The
runtime selects the internal batch optimization only when the resolved tool set
is exactly `read_file`; requesting any additional tool keeps the normal agent
loop while still listing the files in the delegated task:

```json
{
  "task": "Compare the documents and summarize their differences.",
  "files": ["docs/a.md", "docs/b.md"]
}
```

For the batch path:

- `required_tools` defaults to and must resolve to `read_file` only;
- `files` contains 1-32 unique local paths;
- reads run concurrently and must prove complete through structured metadata;
- one selected file is limited to 64,000 characters;
- aggregate selected content is limited to 200,000 characters;
- synthesis uses one tool-free model call;
- `sub_agent_batch_synthesis_timeout_seconds` bounds that call.

Any missing, failed, truncated, unverified, or oversized input returns
`BATCH_FILES_PREFETCH_FAILED` before synthesis. Synthesis timeout returns
`BATCH_SYNTHESIS_TIMEOUT`.

## Budgets

The general-loop defaults and caps come from `tool_limits.sub_agent`:

```yaml
tool_limits:
  sub_agent:
    general_max_steps: 60
    general_max_tool_calls: 32
    no_progress_steps: 6
```

Callers may request smaller `budget.max_steps` and `budget.max_tool_calls`.
Values above the configured limits are clamped. `budget` must be a JSON object,
not serialized JSON text. `sub_agent_token_limit` independently bounds the
child context.

Recoverable artifact workflows keep two ledgers. A parent `sub_agent` call
counts once against the parent workflow's `max_tool_calls`; the child's
internal tool calls count only against the workflow's separate
`max_delegated_tool_calls` aggregate. Exhausting delegated work blocks new
sub-agents but preserves the parent's completion reserve for merge, QA, and
delivery.

## Diagnostics

Successful `ToolResult.raw_output` includes:

- `type: sub_agent_delegation`
- inferred `strategy`
- requested and resolved tools and Skills
- derived constraints and applied defaults
- normalized `files` and effective budget
- model/tool-call counts, usage, and model-routing diagnostics

Pre-execution failures use `type: sub_agent_delegation_error` with a stable
`code`, `retryable`, `invalid_fields`, and correction metadata where relevant.
Child progress uses `rawOutput.type: sub_agent_progress`.

## Ownership and proof

- Request normalization and policy: `box_agent/tools/sub_agent_capabilities.py`
- Execution, batching, and write wrappers: `box_agent/tools/sub_agent_tool.py`
- Session tool assembly: `box_agent/tools/setup.py`
- Regression coverage: `tests/test_sub_agent_capabilities.py`,
  `tests/test_sub_agent_tool.py`, Core, ACP, and config tests
