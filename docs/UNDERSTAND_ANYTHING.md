# Understand Anything Code Map

Box-Agent uses Understand Anything as a local architecture index for code
discovery, ownership tracing, dependency inspection, and guided onboarding. The
graph accelerates navigation, but the source tree, focused tests, logs, and
runtime probes remain the source of truth.

## Repository scope

The shared scope is defined by
[`../.understand-anything/.understandignore`](../.understand-anything/.understandignore).
The current configuration includes the core runtime, ACP adapters, tools,
configuration, examples, and documentation. It intentionally excludes bundled
skill assets, tests, workspaces, virtual environments, and generated output so
the graph stays focused on product architecture.

Only these shared files belong in Git:

- `.understand-anything/.understandignore`
- `.understand-anything/config.json`

Do not commit `knowledge-graph.json`, `meta.json`, fingerprints, intermediate
files, trash directories, dashboard tokens, or caches. They are local generated
artifacts and are ignored by `.gitignore`.

## Refresh workflow

1. Review `.understand-anything/.understandignore` before changing graph scope.
2. Run `/understand --full --language zh` from a client with the Understand
   Anything plugin when the graph is missing, materially stale, or the scope has
   changed. Use `/understand` for a normal incremental refresh.
3. Confirm that validation reports no critical issues and that every analyzed
   file-level node belongs to exactly one architecture layer.
4. Keep `scan-result.json` and the fingerprint baseline locally so later
   incremental refreshes can compare structure efficiently.
5. If the dashboard is launched, open the tokenized URL emitted by the plugin;
   the bare local server URL is not sufficient.

Refresh the graph after changes to entry points, subsystem boundaries, shared
tools, ACP contracts, runtime packaging, or documentation that should appear in
the guided tour. A source-only change does not require committing generated
graph files.

## Verification and review

Use the graph to identify likely files and relationships, then verify important
conclusions with direct file reads, `rg`, focused `uv run pytest` commands, logs,
or runtime probes. If graph metadata does not match the current commit, describe
it as stale until it is refreshed.

Graph-only changes are local maintenance. If shared scope or language settings
change, include the relevant configuration diff and explain the intended
coverage in the pull request's Task, Proof, and Risk sections.
