# Agent Session and Plugin Lifecycle

`AgentSession.open(config=...)` is the managed entry point used by ACP and CLI.
It retains the caller's Config, prepares configured capabilities once, creates
the Agent, and owns session cleanup. Each `run_events()` creates a fresh run
activation from that session's existing runtime. `SessionLog` remains the only
durable session-state source.

## Creation and execution

```mermaid
flowchart TB
    subgraph HOST["Host adapters"]
        ACP["ACP Server<br/>protocol, models, permissions, notifications"]
        CLI["CLI<br/>config/probing, commands, rendering"]
        INPUT["Config + SessionOptions + HostBindings<br/>normalized inputs and borrowed capabilities"]
        ACP -->|"newSession"| INPUT
        CLI -->|"startup"| INPUT
    end
    RUNTIME["Reusable PluginRuntime + PluginHost<br/>static catalog / validation / dependency ordering / scoped activation<br/>ACP application-owned; CLI private by default"]
    subgraph CREATE["Once per session"]
        OPEN["AgentSession.open / SessionState.open"]
        CONTEXT["SessionContext<br/>same Config reference"]
        PREP["PluginRuntime.open_session<br/>activate Process / Session scopes, then prepare"]
        ASSEMBLY["Session plugins → session_assembly<br/>model → memory → tools/Skills/MCP → prompt → hooks"]
        FACTORY["Internal create → AgentService<br/>construct Agent; finish_session restores/binds Skills"]
        SESSION["AgentSession<br/>Config, Agent, PluginSession, live state<br/>ACP subclass: SessionState; state view: AgentRunHandle"]
        INPUT --> OPEN --> CONTEXT --> PREP --> ASSEMBLY --> FACTORY --> SESSION
    end
    subgraph RUN["Each run"]
        OPTIONS["Session.run_events / build_run_options<br/>defaults + session state + explicit overrides"]
        CONTEXT_RUN["RunContext<br/>SessionContext + current Agent + final options"]
        BIND["PluginSession.open_run → run.services<br/>reuse Host/session instances, activate fresh Run scope"]
        SERVICES["ActivatedRegistry → KernelServices<br/>fresh bundle and HookManager"]
        SESSION --> OPTIONS --> CONTEXT_RUN --> BIND --> SERVICES
    end
    subgraph EXEC["Execution and output"]
        AGENT["Existing Agent.run_events"]
        BRIDGE["runtime → core compatibility facade"]
        COMPOSE["composition<br/>validate/forward services and close kernel event stream"]
        KERNEL["AgentLoopKernel"]
        EVENTS["AgentEvent → Agent / Session → host consumer"]
        LEGACY["Legacy direct Agent / synchronous create<br/>unmanaged runs retain a fresh default Host"]
        SERVICES --> AGENT --> BRIDGE --> COMPOSE --> KERNEL --> EVENTS
        LEGACY -.-> AGENT
    end
    RUNTIME -.->|"same Host"| PREP
    RUNTIME -.->|"same Host"| BIND
    ACP -->|"later prompts"| OPTIONS
    CLI -->|"tasks / turns / continuations"| OPTIONS
```

The arrows show lifecycle and call flow. The kernel does not import the session,
Config, PluginHost, or adapters. It receives resolved values and services.
Managed composition does not create a second default Host or dispose resources
owned by the session. It still owns closing the kernel event stream.

## Inputs and configuration timing

| Input | Meaning |
| --- | --- |
| `Config` | Existing configuration object, retained by reference through SessionContext and RunContext |
| `SessionOptions` | Stable workspace cwd, execution/session mode, utility flag, permission policy and session state |
| `HostBindings` | Borrowed model clients, application tool catalog, SkillLoader, memory, hooks, SessionLog, discovery tasks and host callbacks |
| `PluginRuntime` | Optional application-owned runtime shared across sessions; `open` creates a private runtime when omitted |

Constructor settings keep their existing read timing. Step limits, tool limits,
context budget and retry settings resolve when the Agent is constructed.
Existing turn policy continues to read the same Config at turn time. Model
switches and explicit run overrides resolve before the run service bundle is
built. Replacing an adapter's default Config affects future sessions only.
This is not a hot-reload API.

`session_assembly.py` calls the existing capability producers, retaining
ACP/CLI prompt segment ordering, raw tool schemas and ordering, Skill selection
and restoration, memory gates, utility suppression, and deferred MCP timing.
The static initializer list always exists; existing Config gates inside those
initializers decide which resources to prepare. There is no new `plugins`
configuration key or plugin-directory scanning.

## Scope and ownership

| Scope | Ownership and disposal |
| --- | --- |
| Process | One PluginRuntime/Host and explicit process plugins. Process factories receive application context (currently `None`), never a session Config. ACP's existing model pool and discovery resources remain borrowed host capabilities. |
| Session | Config-dependent built-in resources, prompt, tools and Skill state. Created once, isolated by session key, reused across turns. Only resources created by assembly are registered for cleanup. |
| Run | Fresh RunContext, HookManager and KernelServices bound to current options. Activation ends on completion, error, cancellation or early stream closure. |

Descriptors accept either the original no-argument `factory` or
`context_factory(PluginFactoryContext)`. The latter receives its exact scope
context and a read-only mapping of declared dependency IDs to instances.
Dependencies cannot reference a shorter-lived scope. Validation and dependency
ordering precede activation; asynchronous preparation runs outside Host
lifecycle reservations.

Closing a session stops its active run before releasing session resources.
Closing a shared runtime waits for in-flight initialization, closes all sessions,
then closes process resources. Initialization failures roll back; callbacks
interrupted by cancellation remain available for a subsequent `aclose()`.
Ordinary disposer failures are terminal, following PluginHost's existing
semantics. The primary execution error is preserved when cleanup also fails.
Duplicate active session keys and overlapping runs are rejected.

Borrowed clients, catalogs, discovery tasks and SessionLog are closed by their
existing owners. `LLMClient.aclose()` closes its SDK transport; `for_model()`
views sharing that transport must not close it independently.

## Managed Python use

```python
from contextlib import aclosing

from box_agent.agent_session import AgentSession
from box_agent.session_context import SessionOptions

session = await AgentSession.open(
    config=config,
    options=SessionOptions(workspace_dir=workspace),
)
try:
    session.agent.add_user_message(user_text)
    async with aclosing(session.run_events()) as events:
        async for event in events:
            await render(event)
finally:
    await session.aclose()
```

Pass `runtime=shared_runtime` to reuse one Host across multiple sessions, and
close that runtime at application shutdown. Pass `HostBindings` to borrow
already-probed models or other host-owned capabilities. A binding containing
both `tools` and `system_prompt` opts into the prepared-resource contract.

`AgentSession.create(config=..., llm_client=..., system_prompt=..., tools=...)`
remains synchronous and backward compatible. It constructs a session from
prepared resources without managed plugin ownership. Direct `Agent`,
`AgentSession(agent=...)` and `SessionState(agent=...)` remain supported.
Their runs retain the default per-run Host path. Use `session.run_events()`
to run a managed session; direct calls to its Agent bypass managed run ownership.

`AgentRunHandle` remains a view of the same session state. `build_run_options`
binds cancellation, injection and summary/extraction references before explicit
overrides. Managed sessions populate the internal `kernel_services` field;
adapters should not supply it themselves.

## Adapter boundaries

ACP retains request parsing, workspace/model binding, permission reverse RPC,
task registration, initial goals, turn orchestration and event rendering.
`SessionState` inherits the common session and extends it with ACP metadata.
Rebinding closes the old session after workspace validation; failed restoration
releases the unpublished session. Server shutdown closes sessions, background
tasks, owned models and tool runtime resources.

CLI retains configuration setup/probing, terminal input, commands and rendering.
One managed session serves task mode, interactive turns and goal continuations.
`/clear` and `/clear_all` reuse that session. The CLI closes its session and every
model client it created, including probe/reconfiguration clients, on exit.

Skill content loading, matching and MCP discovery retain their existing lazy or
deferred behavior. Moving preparation to session plugins does not eagerly load
every Skill body or connect every MCP server at session start. Host callbacks
and product workflows stay in their owning adapters/capability modules.

## Verification

`test_session_plugins.py`, `test_plugin_runtime_lifecycle.py`,
`test_plugin_host_context.py` and `test_managed_kernel_services.py` cover scoped
reuse, configuration identity, fresh run bindings, failure rollback,
cancellation, consumer closure and compatibility. `test_session_adapter_assembly.py`
checks shared ACP/CLI preparation, ordinary/project/utility prompt and raw tool
schema contracts, restoration failure and ownership. Existing Agent, ACP, CLI,
Skill, prompt and architecture suites remain relevant.

Source tests and ACP source-process probes do not prove packaged host behavior.
A runtime build/install, host restart and fresh live task are separate validation
boundaries.
