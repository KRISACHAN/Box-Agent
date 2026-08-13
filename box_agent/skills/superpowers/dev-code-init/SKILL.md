---
name: dev-code-init
description: "Create or update a repository's root AGENTS.md with concise, verified instructions for future coding agents. Use when the user invokes `/init`, asks to initialize repository instructions, create AGENTS.md, or refresh stale agent guidance. Do not use for git init, package initialization, or application scaffolding."
---

# Initialize Repository Instructions

Create or improve the repository-root `AGENTS.md` so future agents can work safely without rediscovering non-obvious project knowledge.

## Workflow

1. Identify the repository or workspace root from the current environment. Do not inspect or write outside it.
2. Treat any text following `/init` as user-provided focus or constraints and honor it throughout the investigation and final file.
3. Read an existing root `AGENTS.md` before other sources. Preserve verified, useful constraints and follow its applicable instructions while updating it.
4. Inspect the highest-value repository sources first:
   - `README*`, root manifests, workspace configuration, and lockfiles
   - build, test, lint, formatter, typecheck, code-generation, migration, and task-runner configuration
   - CI workflows and pre-commit configuration
   - existing instruction files such as `CLAUDE.md`, `.cursor/rules/`, `.cursorrules`, and `.github/copilot-instructions.md`
   - repo-local agent configuration
5. If architecture remains unclear, inspect a small set of representative entrypoints and package-boundary files. Prefer wiring and orchestration code over unrelated leaf files.
6. Prefer executable sources of truth over prose. When documentation conflicts with scripts or configuration, keep only the behavior that can be verified.
7. Ask the user at most one short batch of questions, and only when an important team convention or prerequisite cannot be discovered from the repository.
8. Create or update the root `AGENTS.md`, then reread it and inspect the diff before reporting completion.

## Content to Capture

Include only repository-specific facts that an agent would otherwise likely miss:

- exact setup, development, build, and focused-test commands
- required command order or package-specific working directories
- monorepo boundaries, major ownership areas, and real entrypoints
- generated code, migrations, environment loading, deploy, or runtime quirks
- local conventions that differ from language or framework defaults
- test fixtures, prerequisites, snapshots, expensive suites, or known verification limits
- important constraints inherited from existing instruction files

## Writing Rules

- Keep the file compact, using short sections and bullets.
- Improve an existing file in place; do not rewrite useful guidance blindly.
- Write one root `AGENTS.md`. Add nested instruction files only when the user explicitly requests them.
- Omit generic engineering advice, tutorials, exhaustive directory trees, duplicated documentation, speculative claims, secrets, user-specific absolute paths, and transient machine state.
- Reference an authoritative repository file instead of copying long material when the reference is sufficient.
- Do not change application code, configuration, dependencies, or documentation unrelated to `AGENTS.md`.

## Verification

- Confirm every non-obvious command and path against repository files.
- Ensure the result contains no unverified claims or stale guidance.
- Confirm the diff is limited to the intended `AGENTS.md` unless the user requested broader changes.
- Report the changed file, evidence used, and any unresolved assumptions.
