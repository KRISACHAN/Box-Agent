# Repository Guidelines

## Project Structure & Module Organization

`box_agent/` contains the application code: `agent.py` drives the execution loop, `cli.py` exposes the CLI, `llm/` wraps model providers, `tools/` holds built-in tools, `acp/` hosts the ACP server, and `config/` stores example config files. `tests/` contains the automated test suite, with files such as `test_agent.py` and `test_mcp.py`. `examples/` provides runnable demos, while `docs/` and `docs/assets/` hold contributor-facing documentation and images. Treat `workspace/` as runtime scratch space, not committed source.

## Code Discovery & Understand Anything

For architecture, ownership, dependency, onboarding, and change-impact questions,
use this default order:

1. Check the committed `.understand-anything/knowledge-graph.json` and read its
   `project.gitCommitHash` as the analyzed source baseline. Compare that
   baseline with later source changes before treating the graph as current.
   Cross-check `.understand-anything/meta.json` for the refresh timestamp,
   baseline commit, graph version, and analyzed file count. If present, inspect
   `.understand-anything/last-run-summary.json` for refresh status.
2. Use `.understand-anything/knowledge-graph.json`, or the most relevant
   `.understand-anything/domain-graphs/*knowledge-graph.json` when such a graph
   exists, as the initial codebase index.
3. Extract only the relevant nodes, edges, layers, or tour steps with `jq`,
   `rg`, or a focused keyword search. Do not load or summarize the entire graph
   when a narrow query is sufficient.
4. Open the smallest useful set of real source files and verify the graph-based
   conclusion with direct reads, `rg`, focused tests, logs, or runtime probes as
   appropriate.

Treat every graph as a navigation index, not the source of truth. If the graph,
metadata, or tooling is missing or stale, state the limitation and continue
with normal source search when the task can still proceed; recommend a refresh
when it would materially improve the result.

Keep the shared `.understand-anything/knowledge-graph.json`, `meta.json`,
`fingerprints.json`, `.understandignore`, and `config.json` in Git. The graph,
metadata, and fingerprints form one refresh baseline and must be regenerated
and reviewed together; do not hand-edit them. Keep `last-run-summary.json`,
intermediate files, dashboard tokens, trash, and caches local. Add any future
shared domain graph to Git intentionally together with its scope documentation.

## Build, Test, and Development Commands

Use `uv` for local development.

- `uv sync`: install project and dev dependencies from `pyproject.toml` and `uv.lock`.
- `uv run python -m box_agent.cli`: run the CLI in development mode.
- `uv tool install -e .`: install `box-agent` and `box-agent-acp` as editable local commands.
- `pytest tests/ -v`: run the full test suite.
- `pytest tests/test_agent.py -v`: run a focused subset while iterating.

If you need bundled skills, run `git submodule update --init --recursive` before testing skill-related changes.

## Coding Style & Naming Conventions

Follow PEP 8 with 4-space indentation. Use type hints for public functions and async interfaces. Keep modules and functions in `snake_case`, classes in `PascalCase`, and test files named `test_<area>.py`. Match the existing style in `box_agent/tools/` and `box_agent/llm/`: short docstrings where needed, small focused helpers, and minimal unrelated refactors.

## Testing Guidelines

Pytest is the test runner, with `pytest-asyncio` enabled for async tests. Add or update tests for every behavior change, especially around tool execution, MCP loading, session memory, and CLI flows. Name tests after observable behavior, for example `test_bash_tool_rejects_outside_workspace`. There is no stated coverage gate, but changed code should have direct regression coverage.

## Collaboration & Review Rules

Use TPR in every non-trivial PR description: Task (what changed and what is out of scope), Proof (tests, probes, logs, screenshots, or generated-manifest checks), and Risk (compatibility, packaging, migration, config, or rollback notes). Keep PRs scoped to one behavior or subsystem. For shared behavior, prefer changes in the shared core (`core.py`, shared tools, config, or schema) and keep CLI / ACP code as thin adapters. If a change affects packaged runtime behavior used by officev3, call out whether source-only tests are enough or whether a runtime rebuild/install/probe is required.

## Commit & Pull Request Guidelines

Recent history uses conventional-style subjects such as `feat(cli): ...`, `fix(skill): ...`, and `docs: ...`. Keep commits small and scoped. For pull requests, include a clear summary, link related issues when applicable, note config or skill-submodule impacts, and list the test command(s) you ran. Update `README.md`, `CONTRIBUTING.md`, or `docs/` when user-facing behavior changes.
