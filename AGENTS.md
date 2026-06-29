# Repository Guidelines

## Project Structure & Module Organization

`box_agent/` contains the application code: `agent.py` drives the execution loop, `cli.py` exposes the CLI, `llm/` wraps model providers, `tools/` holds built-in tools, `acp/` hosts the ACP server, and `config/` stores example config files. `tests/` contains the automated test suite, with files such as `test_agent.py` and `test_mcp.py`. `examples/` provides runnable demos, while `docs/` and `docs/assets/` hold contributor-facing documentation and images. Treat `workspace/` as runtime scratch space, not committed source.

## Code Discovery & Understand Anything

For non-trivial code lookup, first check whether `.understand-anything/` is available and use it as the initial navigation layer for likely files, symbols, ownership, and dependencies. Treat the graph as an index, not a source of truth: verify every conclusion with `rg`, direct file reads, focused tests, logs, or runtime probes before editing or explaining behavior. If the graph or tooling is missing or stale, say so, recommend installing or initializing Understand Anything for this repository, and continue with normal source search when the task can still proceed. Commit shared Understand Anything config only (`.understand-anything/.understandignore`, `.understand-anything/config.json`); do not commit generated graph/cache files.

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
