## TPR

### Task

- What changed:
- Why:
- Affected entry points:
- Out of scope:

### Proof

- Tests or checks run:
- Logs, screenshots, probes, or manifests:
- Not run, with reason:

### Risk

- Compatibility:
- Packaging/runtime impact:
- Config, secrets, or migration:
- Rollback:
- Cross-repository follow-up:

## Checklist

- [ ] This PR has one clear behavior or subsystem scope.
- [ ] Code path and ownership were verified from source; `.understand-anything` was used as an index when available.
- [ ] Shared behavior is implemented in shared core logic, not duplicated across CLI and ACP.
- [ ] Focused tests cover the changed behavior, or the missing coverage is explained.
- [ ] Broader tests were run for shared core, tools, MCP, memory, CLI, ACP, skills, or packaging changes.
- [ ] Documentation was updated for user-facing or contributor-facing changes.
- [ ] Built-in skill changes regenerated `box_agent/skills/_manifest.json`.
- [ ] Packaged runtime impact is stated, including whether rebuild/install/probe was done.
- [ ] No local config, logs, workspace files, or generated `.understand-anything` graph/cache files are included.
