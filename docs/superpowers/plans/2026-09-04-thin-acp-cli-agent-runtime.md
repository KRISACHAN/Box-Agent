# Thin ACP/CLI Agent Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with TDD checkpoints.

**Goal:** Incrementally remove accidental duplication from ACP and CLI while preserving all public APIs, host-specific behavior, and the completed Agent Loop Kernel.

**Architecture:** Add a host-neutral runtime assembly module one concern at a time. Keep ACP/CLI entry functions and test-visible methods as delegation wrappers; move only protocol-independent construction and control logic. Keep `core.py` as a compatibility facade and do not modify `box_agent/kernel/loop.py`.

**Tech Stack:** Python 3.11+, dataclasses/types, pytest, pytest-asyncio, existing `LLMClient`, permission, memory, MCP, Skill, Agent, and SessionLog implementations.

**Spec:** `docs/superpowers/specs/2026-09-04-thin-acp-cli-agent-runtime-design.md`

## Global Constraints

- Preserve ACP wire messages, CLI output, prompt text/order, tool names/order, session state fields, event order, StopReason, persistence, and error/log behavior.
- Do not change `AgentLoopKernel`, `runtime.py` public signatures, `core.py` compatibility exports, `Agent.run_events()`, or `Agent.run()` behavior.
- Keep `SessionState`, `BoxACPAgent._run_turn`, and CLI test monkeypatch points until all consumers are migrated and deletion gates pass.
- Retain legitimate host specialization: CLI retry/probe/interactive UX; ACP model binding, deferred MCP/Skill, reverse RPC, and filesystem policy.
- Do not introduce a CLI/ACP mode flag that hides divergent policy in a shared helper.
- Every production change starts with a failing behavior test and is followed by focused verification and a diff audit.

---

### Task 0: Capture the pre-refactor behavior baseline

**Files:**
- Create: `tests/test_agent_runtime.py`
- Inspect: `tests/test_acp.py`, `tests/test_cli_runtime.py`, `tests/test_core.py`, `tests/test_kernel_compatibility.py`, `tests/test_llm_activity.py`

**Interfaces:**
- Produces the fixture shape used by all later parity tests: fake LLM/tool event sequence, StopReason, message history, and captured construction kwargs.

- [x] **Step 1: Run existing focused suites before production edits**

Run:

```powershell
uv run pytest tests/test_acp.py tests/test_cli_runtime.py tests/test_architecture_boundaries.py tests/test_core.py tests/test_kernel_compatibility.py tests/test_llm_activity.py -q
```

Expected: record the exact pass/fail counts and any pre-existing failure; do not change source to repair an unrelated baseline failure.

- [x] **Step 2: Add a baseline note to the implementation review**

Baseline recorded on 2026-09-04: `366 passed, 16 failed, 1 skipped` in the focused
suite. The failures are existing environment/state/path/artifact issues (for
example stale SessionLog workspace paths, Windows path separators, and artifact
classification); none is attributed to the LLM wrapper. Current test-visible
compatibility points include ACP `SessionState`/`_run_turn` monkeypatches, CLI
`LLMClient` monkeypatches, and core compatibility imports. This task changes no
production behavior.

### Task 1: Add a host-neutral LLM client construction wrapper

**Files:**
- Create: `box_agent/agent_runtime.py`
- Create: `tests/test_agent_runtime.py`
- Modify: `box_agent/cli.py` at current `LLMClient` construction sites
- Modify: `box_agent/acp/__init__.py` at `run_acp_server` bootstrap construction

**Interfaces:**
- Produces `build_llm_client(...)` with the same keyword values as the existing `LLMClient(...)` call.
- Consumes an explicit `client_factory` so existing `cli.LLMClient` and `acp.LLMClient` monkeypatch points remain effective.

- [x] **Step 1: Write the failing wrapper contract test**

```python
def test_build_llm_client_forwards_all_transport_arguments():
    captured = {}

    class CaptureClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    client = build_llm_client(
        client_factory=CaptureClient,
        api_key="key",
        provider=LLMProvider.OPENAI,
        api_base="https://example.test/v1/",
        model="model-a",
        retry_config=None,
        max_output_tokens=123,
        auth_file="auth.json",
        timeout=17.5,
    )

    assert isinstance(client, CaptureClient)
    assert captured == {
        "api_key": "key",
        "provider": LLMProvider.OPENAI,
        "api_base": "https://example.test/v1/",
        "model": "model-a",
        "retry_config": None,
        "max_output_tokens": 123,
        "auth_file": "auth.json",
        "timeout": 17.5,
    }
```

- [x] **Step 2: Run the new test and observe the expected missing-symbol failure**

Run: `uv run pytest tests/test_agent_runtime.py::test_build_llm_client_forwards_all_transport_arguments -q`

Expected: FAIL because `box_agent.agent_runtime.build_llm_client` does not yet exist.

- [x] **Step 3: Implement the minimal wrapper**

```python
def build_llm_client(*, client_factory=LLMClient, retry_callback=None, **kwargs):
    client = client_factory(**kwargs)
    if retry_callback is not None:
        client.retry_callback = retry_callback
    return client
```

Use precise type aliases and the existing `LLMClient` type in the real implementation; do not normalize values or change retry semantics.

- [x] **Step 4: Add callback and disabled-retry preservation tests**

Assert that a callback is assigned only when explicitly supplied and that `retry_config=None` remains `None`. Assert that a preconfigured client factory still receives the exact provider enum, URL, model, token cap, auth file, and timeout.

- [x] **Step 5: Run the wrapper tests and verify GREEN**

Run: `uv run pytest tests/test_agent_runtime.py -q`

Expected: all new wrapper tests pass with no warnings.

- [x] **Step 6: Replace only the duplicated adapter construction calls**

In CLI and ACP, call `build_llm_client(client_factory=LLMClient, ...)` with the existing kwargs. Keep probe/no-retry clients, retry callbacks, setup-wizard branches, and ACP `SessionBoundLLM` logic in their original functions. Do not remove the imported `LLMClient` names.

- [x] **Step 7: Run adapter regression tests**

Run:

```powershell
uv run pytest tests/test_agent_runtime.py tests/test_acp.py tests/test_cli_runtime.py tests/test_architecture_boundaries.py -q
```

Expected: the same public-path assertions, monkeypatch captures, event sequence, and StopReason remain green.

- [x] **Step 8: Review the diff before moving on**

Run `git diff --check` and inspect every changed call site. Confirm no probe, setup, callback, model binding, log, or error branch disappeared. If a call site cannot use the wrapper without losing a detail, leave it unchanged and record why.

### Task 2: Share permission engine construction without sharing transports

**Files:**
- Modify: `box_agent/agent_runtime.py`
- Create/modify: `tests/test_agent_runtime.py`
- Modify: `box_agent/cli.py` permission assembly
- Modify: `box_agent/acp/__init__.py` session permission assembly

**Interfaces:**
- `build_permission_engine(policy, workspace_dir, *, grant_store, engine_factory)` forwards the already-resolved policy and grant store to the existing engine constructor.
- Keep `CLIPermissionNegotiator` and ACP `_PermissionNegotiator` transport, timeout, rendering, policy resolution, and reverse-RPC code unchanged.

- [x] **Step 1: Add failing forwarding test**

`tests/test_agent_runtime.py` captures the policy, workspace path, and grant store passed to a test engine factory. This test first failed at collection because the helper did not exist.

- [x] **Step 2: Implement the smallest pure helper and run its focused tests**

The helper forwards explicit inputs and does not move policy decisions into a mode branch. `tests/test_agent_runtime.py` reports `3 passed`.

- [x] **Step 3: Convert both adapter constructor calls through compatibility wrappers**

CLI and ACP now call the helper with their existing `PermissionEngine` symbols, so monkeypatching and host-specific policy branches remain intact.

- [x] **Step 4: Run permission and boundary regressions**

The selected permission/ACP/CLI/boundary suite reports `27 passed`. The broader baseline failures remain unrelated environment/path/artifact failures.

Additional safe construction slices are complete: `build_memory_manager(...)`
and `build_memory_extractor(...)` centralize shared constructors while leaving
CLI import/maintenance ordering and ACP background/session timing unchanged.
Their forwarding behavior is covered by `tests/test_agent_runtime.py`.

`build_agent(...)` is now also the shared constructor forwarding boundary. It
keeps the existing adapter-resolved prompt/tools/hooks/session-log inputs and
preserves the injectable `Agent` factory used by tests and downstream hosts.
Its optional `hooks` and `session_log` parameters use an explicit unset
sentinel so an adapter's historical explicit-`None` call shape is retained.

The narrow `box_agent.agent_service.AgentService` facade now owns the final
Agent construction boundary while delegating to `build_agent(...)`. ACP
resolves its historical module-level `Agent` hook at each session creation;
CLI resolves it at runtime startup, so existing monkeypatch points and
constructor kwargs remain intact.

### Task 3: Centralize prompt/context segments

**Files:**
- Create: `box_agent/project_context.py`
- Create: `box_agent/env_context.py`
- Create/modify: `tests/test_project_context.py`
- Modify: `box_agent/cli.py` prompt assembly
- Modify: `box_agent/acp/__init__.py` `_build_session_prompt`
- Modify: `box_agent/acp/project_context.py`, `box_agent/acp/env_context.py` only through compatibility re-exports

**Interfaces:**
- A pure composer returns ordered prompt segments and leaves host-specific overlays to the caller.

Progress note: the first safe slice is complete. `box_agent/project_context.py` now
owns the protocol-independent project-startup implementation; CLI and ACP import
it, while `box_agent/acp/project_context.py` remains a compatibility re-export.
The larger prompt composer is intentionally not extracted in the same change.

The environment-context contract has received the same safe move: the exact
implementation now lives in `box_agent/env_context.py`, both adapters import the
neutral path, and `box_agent/acp/env_context.py` re-exports the historical
classes, sanitizers, and renderer names.

Prompt spacing retains an explicit `skip_empty=False` escape hatch for legacy
file-backed mode prompts that historically left a separator even when empty.

The prompt slice now also centralizes the exact project-workspace segment and
provides `compose_prompt_segments(...)` for ordered placeholder/optional
segment composition.  ACP and CLI use it for their common project-startup and
runtime segments; host-specific filesystem, layout, expert, logging, and mode
prompt branches remain local.

- [x] **Step 1: Snapshot existing CLI and ACP prompt outputs**

Use representative workspace, artifact, environment, memory, and Skill inputs. Assert exact segment ordering and fallback text before extraction.

- [x] **Step 2: Write failing composer tests**

Include empty/absent optional segments, path/layout data, and ACP expert/filesystem hints. The expected output must match the snapshots exactly.

- [x] **Step 3: Implement the composer and preserve old builder names as wrappers**

Move only protocol-independent value objects/builders out of `acp/`; preserve import paths during migration.

- [x] **Step 4: Run prompt, ACP, and CLI tests; audit default text and whitespace**

Do not unify different fallback text in this task unless a parity test proves they were already equal.

### Task 4: Share Goal/Skill/MCP turn preparation

**Files:**
- Create: `box_agent/turn_runtime.py`
- Create/modify: `tests/test_turn_runtime.py`
- Modify: `box_agent/cli.py` turn preparation/autopilot helpers
- Modify: `box_agent/acp/__init__.py` turn preparation/autopilot helpers

**Interfaces:**
- Pure `prepare_skill_turn(...)` returns preload/prompt/hash metadata.
- `run_goal_autopilot(...)` owns only continuation budget/no-progress calculation and accepts host callbacks.
- `MCPRuntimeController` exposes atomic refresh/reconcile operations; blocking/deferred scheduling stays in adapters.

Progress note: the pure Goal slice is complete in `box_agent/goal_runtime.py`.
Budget and no-progress calculations are now used by both adapters.  Skill
preload state and MCP eager registry reconciliation have since moved into
protocol-independent helpers, while host scheduling and reporting remain local.

The first Skill slice is now complete in `box_agent/turn_runtime.py`:
`sync_skill_cache_fingerprint_context(...)` is shared by the ACP session state
and CLI turn closures, while selector updates, preload warnings, attribution,
and host rendering remain in their original adapters.

- [x] **Step 1: Add failing parity tests for Skill, Goal, and MCP policy differences**

Assert identical generic calculations and distinct CLI/ACP callbacks/scheduling. Assert Goal mutations still call the existing `Agent` API.

- [x] **Step 2: Implement one controller at a time with old function wrappers**

Keep CLI sidecar persistence, ACP metadata, deferred updates, and terminal messages unchanged.

- [x] **Step 3: Run focused tests after each controller**

Required suites: `tests/test_acp.py`, `tests/test_cli_runtime.py`, and the new controller tests.

The current Skill slice adds `box_agent.skill_runtime.apply_auto_loaded_skill_state(...)`.
It owns only the shared collection transition (names, hashes, and optional
attributions) and preserves list/dict identities; ACP warnings/attributions and
CLI terminal reporting remain adapter-specific.  Goal pure helpers and cache
fingerprint projection are already shared.  The MCP slice adds
`box_agent.mcp_runtime.sync_mcp_registries(...)` for the existing eager
base/session reconciliation; deferred loading, auth lifecycle, and ACP runtime
notifications remain adapter-specific.

The next Skill slice adds `prepare_auto_loaded_skills(...)`, combining the
protocol-independent prompt builder with that state transition while leaving
host reporting untouched; the helper accepts the historical adapter builder
hook so existing monkeypatches remain effective.  `MCPRuntimeController` now
owns the current base and per-session registry targets while accepting the
historical sync operation hooks; ACP readiness/deferred/auth scheduling still
stays in the adapter.  `GoalAutopilotController` owns continuation counters,
budget exhaustion, and no-progress state; both ACP and CLI retain their exact
turn invocation, logging, and output branches.

Task 4's implementation gate is now complete for shared calculation/state
ownership; the remaining adapter-only scheduling and terminal/ACP metadata
paths are intentionally retained for compatibility.

The observer slice adds `RunObserver`, `ArtifactObserver`, and
`cleanup_turn_resources` in `box_agent.run_observer`; ACP keeps its usage
payload construction, wire notification mapping, artifact envelope, and
cleanup logging callbacks, while usage accumulation, trace forwarding,
artifact registration, and ordered resource cleanup are reusable by other
adapters.

The CLI rendering slice adds `box_agent.cli_renderer.CliRenderer` and moves
the terminal-only event mapping and shared ANSI palette there. `Agent.run()`
and its legacy `_render_event`/`_render_memory_search` entry points remain
intact and delegate to the renderer; ACP rendering is unchanged.

### Task 5: Introduce Run Handle state aliases and extract generic turn lifecycle

**Files:**
- Create: `box_agent/agent_run.py`
- Create/modify: `tests/test_agent_run.py`
- Modify: `box_agent/acp/__init__.py` `SessionState` and `_run_turn`
- Modify: `box_agent/cli.py` only where it prepares `AgentRunOptions`

**Interfaces:**
- `AgentRunHandle` owns shared state references and `AgentRunOptions`; adapters use the
  protocol-independent observer and cleanup helpers when assembling a run.
- ACP `SessionState` remains a compatibility facade; `_run_turn` remains monkeypatchable and callable with its old signature.

- [x] **Step 1: Add failing tests for single owner of cancel/inject/goal/skill state**

Exercise old ACP fields and new handle properties together; assert they refer to the same underlying objects and preserve cancellation behavior.

- [x] **Step 2: Implement aliases before deleting any field**

Use properties or shared object references. Do not alter session IDs, task IDs, trace IDs, errors, or ACP metadata.

The first migration slice adds `box_agent.agent_run.AgentRunHandle` as a
protocol-independent proxy over ACP `SessionState`.  `SessionState` keeps every
legacy field and now creates one handle that aliases cancellation, injection,
turn, Goal, and Skill state.  No `_run_turn` call shape or event path changed;
`_run_turn` now reads its generic cancellation, injection, turn, and Skill
references through that proxy and snapshots `AgentRunOptions` through its
generic `build_run_options` entry point.  Later slices can move remaining
consumers to the handle before removing compatibility fields.

- [x] **Step 3: Extract generic usage/trace/artifact/cleanup observer**

Leave ACP event-to-wire mapping, reverse RPC, task metadata, and stop-reason conversion in ACP.

- [x] **Step 4: Run all ACP compatibility tests that monkeypatch or call `_run_turn` directly**

Expected: no test needs to change its old call shape.

### Task 6: Keep CLI rendering adapter-specific while preserving `Agent.run()`

**Files:**
- Create: `box_agent/cli_renderer.py`
- Create/modify: `tests/test_cli_renderer.py`
- Modify: `box_agent/agent.py` only to inject/delegate a default renderer
- Modify: `box_agent/cli.py` interactive rendering path

**Interfaces:**
- CLI renderer consumes `AgentEvent` and produces the current terminal output.
- `Agent.run()` remains a compatibility wrapper with identical default output.

- [x] **Step 1: Snapshot representative terminal event rendering**

Cover text, thinking, tool call/result, activity, error, finish, artifact, and cancellation events.

- [x] **Step 2: Write failing renderer extraction tests**

Assert exact output and color/reset behavior for the existing event cases.

- [x] **Step 3: Move implementation behind the renderer and retain the Agent wrapper**

Do not change ACP rendering or event contracts.

### Task 7: Core compatibility and final deletion audit

**Files:**
- Modify: `box_agent/core.py` only if a compatibility alias needs adjustment
- Modify: `tests/test_architecture_boundaries.py`
- Add/update focused parity tests from prior tasks

- [x] **Step 1: Add boundary assertions for new runtime modules**

Ensure adapters use Agent/runtime/service boundaries and do not import Kernel implementation modules directly.

- [x] **Step 2: Run the complete focused verification matrix**

```powershell
uv run pytest tests/test_acp.py tests/test_cli_runtime.py tests/test_architecture_boundaries.py tests/test_core.py tests/test_kernel_compatibility.py tests/test_llm_activity.py -v
git diff --check
```

- [x] **Step 3: Perform the deletion gate for each candidate duplicate**

Use `rg` to check production/test/docs/config references, compare old/new event and state snapshots, and delete only code that is now an unreferenced implementation body behind a tested wrapper.

- [x] **Step 4: Report runtime boundaries separately**

Report source tests, build/install, probe, host restart, and live-task verification as separate states. Do not claim packaged ACP/CLI behavior from source tests alone.

## Verification refresh — 2026-09-08

### Target and preservation audit

- Updated the local `main` and rebased this branch onto `origin/main` at
  `56ee3903d587864c75c65911ede6dd28cf5dfe80`. Retained upstream's newer kernel
  extraction and lifecycle fixes instead of replaying the superseded extraction.
- `git diff origin/main -- box_agent/core.py box_agent/kernel
  box_agent/composition.py box_agent/plugins box_agent/runtime.py` is empty.
- Independent read-only review covered the neutral modules, ACP/CLI call sites,
  original constructor hooks, prompt composition, cancel/inject references,
  Skill limits, usage, artifact metadata and cleanup ordering. No unresolved
  actionable runtime regression was identified. Static trace-directory chooser
  routing found during review was fixed and regression-tested separately.
- Compatibility wrappers remain intentional. This does not complete the larger
  session-ownership or all-capability-assembly migration described in the spec.

### Deterministic checks

With fresh, matching `HOME` and `USERPROFILE` directories, the final focused run
using `uv run --no-sync python -m pytest` covered these files:

```text
tests/test_agent_runtime.py tests/test_agent_service.py tests/test_agent_run.py
tests/test_goal_runtime.py tests/test_mcp_runtime.py tests/test_project_context.py
tests/test_env_context.py tests/test_turn_runtime.py tests/test_run_observer.py
tests/test_cli_renderer.py tests/test_trace_viewer.py tests/test_trace_viewer_server.py
```

Result: **99 passed**. `node --test tests/js/*.test.js`: **19 passed**.
`python -m compileall -q box_agent` and `git diff --check` also passed.

The broader same-environment parity run used ACP, CLI runtime, Skill runtime,
core, kernel compatibility, LLM activity and architecture-boundary suites:

- Baseline: **434 passed, 14 failed, 1 skipped**.
- Current: **438 passed, 15 failed, 1 skipped**. The same 14 failures occurred;
  the additional liveness timing failure did not reproduce when the complete
  LLM activity file was rerun separately: **6 passed** on each version.

The Windows full-suite run used `pytest tests/ -q --tb=short -n 4`, excluding
`tests/test_mcp.py::test_connection_timeout_on_unreachable_server`:
**3330 passed, 71 failed, 142 skipped**. This is **not a green full-suite gate**.
Of those 71 failures, 23 were reproduced on the baseline; 3 high-priority
ACP/tool-engine cases passed on both versions in isolated reruns (session writer
lock contention and timing). The other 45 were not individually baseline-rerun;
they must not be described as proven baseline failures. Logs point to Windows
path/shell assumptions, permissions, dependencies and existing assertions.

### Prompt parity

- Actual ACP `_build_session_prompt` output was byte-identical in 8 controlled
  variants spanning general, analysis, project/code, environment, expert,
  empty mode-file and memory-related composition.
- Actual CLI `run_agent` Agent-construction captures were byte-identical in
  4 controlled variants: general/code workspace with sandbox on/off. External
  capabilities were stubbed in this offline probe, not exercised as live tools.
- System/code/analysis prompt assets are unchanged from the target.
- Real-model first-request comparisons separately cover full system text,
  ordered messages and tool schemas: **22/22 same-entrypoint pairs matched**.
  Normalize only exact run-specific paths
  and generated transport IDs; preserve whitespace, dates, numeric values and
  semantic content. Later messages may diverge after non-deterministic model
  outputs and tool results; they are not expected to be identical transcripts.

### Build and runtime boundary

`uv build --out-dir workspace/verification-20260908/dist` produced a wheel and
sdist. The wheel contains the new modules and current trace UI, with no
`workspace/` entries. A `uv pip install --no-deps --target ...` scratch install
and isolated import probe resolved `AgentService`, `AgentRunHandle`, CLI and ACP
from the wheel. This is not an officev3 bundle installation or host restart.
`uv sync --frozen --all-extras` did not complete and was cancelled; the existing
environment was used for the checks above. Locked-extra reproducibility and
fresh packaged-host tasks remain unverified.

### Live E2E scope and evidence limitations

The supplied spreadsheet revision 6998 contains 18 cases. Eleven cases without
missing attachments were scheduled through both CLI and ACP on the baseline
worktree and current source (44 runs). Seven cases remain blocked on input
attachments or associated prerequisites; a supplied attachment download returned
HTTP 403. Original case prompts were not rewritten into smaller tasks.

Final accounting: 72 combination records, 44 executed traces and 28 blocked
records. All 22 CLI processes exited 0; 18 ACP turns returned `end_turn` but
their server shutdown exit codes were 1. Four ACP runs timed out (one current,
three baseline). Excluding metadata and runtime caches, 15 runs produced
business files, not independently accepted final deliverables. No case is
claimed as independently accepted by this audit.

Each run records source-file hashes and uses a separate workspace and home.
The bounded setup uses the requested model, main-call thinking/high, 12 steps,
180 seconds wall time, no retries, no Goal autopilot, no memory or subagents,
and no configured MCP servers. Plan/Todo/Skills remain enabled. ACP cancels
permission escalations. CLI runs with sandbox disabled; ACP retains its sandbox
tools. Those limitations must accompany any business-level interpretation.

The local `workspace/verification-20260908/` evidence includes raw results,
traces, exact-input snapshots, prompt parity and derived outcome audits. Keep
these files local: they contain business inputs and generated runtime state.
The trace viewer compares `baseline-acp`, `baseline-cli`, `current-acp`, and
`current-cli` in one source root. CLI lifecycle markers are explicitly labelled
as harness observations; CLI's viewer `incomplete` label is not an exit-code
assertion or a fabricated native stop reason.

Do not equate `end_turn`, process exit, or file presence with task acceptance.
In particular, task-registry JSON and pip caches are not deliverables. The raw
harness classification did not exclude all such files; the derived outcome
audit does, and preserves raw evidence. ACP service shutdown return codes are
reported separately from successful protocol turn responses.

Both versions' main calls use `reasoning_effort=high`; the existing auxiliary
`turn_continuation_judge` sends `none`, which this endpoint rejects with HTTP
422 (it accepts low/medium/high). This is a shared provider-compatibility
limitation, not a prompt change introduced by this extraction. Several tasks
stop at plans, blocked tools or timeouts; full business E2E acceptance remains
open and requires the missing inputs/capabilities and follow-up execution.
The final HTTP audit counted 134 main requests returning 200 and 40 auxiliary
judge requests returning 422. No API credentials or raw business cases are
included in this commit.
