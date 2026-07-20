# Output Contract

## Directory

All outputs must be under:

```text
{workspace}/research/
```

## Citation Format

Use Markdown footnotes:

```markdown
This claim has evidence.[^stable-id]

[^stable-id]: Source title. Publication date. https://example.com
```

For file-only evidence:

```markdown
The source file says this.[^file-a-p3]

[^file-a-p3]: File: strategy.pdf, page 3, section "Market risks".
```

Rules:

- Reuse the same id for the same URL or file section.
- Every inline marker must have a definition.
- Every definition should map to one source.
- Keep verbatim excerpts short.
- Preserve source dates; if no date exists, write `N.D.`.

## Required Artifact Shapes

### Validation Report

After the Markdown artifacts are complete, run the bundled validator with
`--report {workspace}/research/qa/{topic}_research_check.json`. The report is
the machine-readable handoff to downstream presentation/report workflows and
contains `ok`, route, topic, actual/minimum dimension counts, checked files,
issues, and warnings. Do not create this JSON by hand. If any checked research
file changes, rerun the validator so the report is newer than its inputs.

### File Analysis

```markdown
# [Topic] File Analysis

Route: C or D
Time Check: [timestamp]
Constraints: [file-only or file-augmented]

## File Inventory
| File | Type | Size | Summary |

## Per-File Extraction

## Cross-File Mapping

## Gaps

## Consolidated Themes
```

### Cross-Verification

```markdown
# [Topic] Cross-Verification

Route: [A/B/C/D]
Evidence Budget: [actual searches/files/dimensions]

## High Confidence

## Medium Confidence

## Low Confidence

## Conflict Zones

## Validation Updates
```

### Targeted Validation

Optional per-conflict output before the main agent merges updates into
`{topic}_cross_verification.md`.

```markdown
# [Topic] Validation [NN]

Conflict: [short conflict statement]
Evidence Checked: [sources/files searched or inspected]
Resolution: [resolved / narrowed / unresolved]
Confidence: [high / medium / low]
Merge Notes: [exact update recommended for cross-verification]
```

### Final Markdown

Use when no downstream writing skill is available:

```markdown
# [Topic]

## Executive Summary

## Verified Findings

## Conflict Zones

## Derived Insights

## Method and Evidence Limits

## Sources
```
