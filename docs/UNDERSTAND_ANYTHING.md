# Understand Anything Code Map

Box-Agent uses Understand Anything as a versioned architecture index for code
discovery, ownership tracing, dependency inspection, and guided onboarding. The
graph accelerates navigation, but the source tree, focused tests, logs, and
runtime probes remain the source of truth.

## Repository scope

The shared scope is defined by
[`../.understand-anything/.understandignore`](../.understand-anything/.understandignore).
The current configuration includes the core runtime, ACP adapters, tools,
configuration, examples, documentation, and the controlled PPTX compiler under
`box_agent/skills/document-skills/pptx/`. Other bundled skill assets, tests,
workspaces, virtual environments, generated output, and vendored PPTX runtime
payloads remain excluded so the graph stays focused on product architecture.

Only these shared files belong in Git:

- `.understand-anything/.understandignore`
- `.understand-anything/config.json`
- [`.understand-anything/knowledge-graph.json`](../.understand-anything/knowledge-graph.json)

The versioned `knowledge-graph.json` lets contributors explore the same
architecture snapshot immediately after cloning the repository. Do not commit
`meta.json`, fingerprints, intermediate files, trash directories, dashboard
tokens, or caches. Those files are local refresh state and remain ignored by
`.gitignore`.

## Explore the shared graph

After cloning the repository, run `/understand-dashboard` from a client with the
Understand Anything plugin. The dashboard reads the committed
`.understand-anything/knowledge-graph.json`; open the tokenized URL printed by
the plugin. The JSON file can also be inspected directly by other graph-aware
tools without running a refresh first.

## Refresh workflow

1. Review `.understand-anything/.understandignore` before changing graph scope.
2. Run `/understand --full --language zh` from a client with the Understand
   Anything plugin when the graph is missing, materially stale, or the scope has
   changed. Use `/understand` for a normal incremental refresh.
3. Confirm that validation reports no critical issues and that every analyzed
   file-level node belongs to exactly one architecture layer.
4. Update the versioned `knowledge-graph.json` after validation succeeds. Keep
   this generated graph change reviewable and do not hand-edit it.
5. Keep `scan-result.json` and the fingerprint baseline locally so later
   incremental refreshes can compare structure efficiently.
6. If the dashboard is launched, open the tokenized URL emitted by the plugin;
   the bare local server URL is not sufficient.

Refresh the graph after changes to entry points, subsystem boundaries, shared
tools, ACP contracts, runtime packaging, or documentation that should appear in
the guided tour. Small source changes that do not affect graph structure or the
guided tour do not require an immediate graph refresh.

## Verification and review

Use the graph to identify likely files and relationships, then verify important
conclusions with direct file reads, `rg`, focused `uv run pytest` commands, logs,
or runtime probes. Compare the graph's analyzed baseline with later source
changes; describe the graph as stale when those changes affect its architecture
or guided tour.

The graph's `project.gitCommitHash` identifies the analyzed source baseline. A
dedicated graph commit normally follows that baseline commit, so this hash can
legitimately point to the graph commit's parent. For graph updates, include
validation statistics and remaining warnings in the pull request's Task, Proof,
and Risk sections. If shared scope or language settings change, include the
relevant configuration diff and explain the intended coverage.
