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

### Entity-Bound Evidence Ledger

Create `{topic}_evidence.json` before validation:

```json
{
  "schema_version": 1,
  "topic": "topic-slug",
  "target_entities": [
    {
      "entity": "Example Corp",
      "aliases": ["Example"],
      "official_domains": ["example.com"]
    }
  ],
  "evidence": [
    {
      "entity": "Example Corp",
      "claim": "Example Corp launched Product One in 2026.",
      "source_url": "https://example.com/news/product-one",
      "source_type": "first_party",
      "evidence_excerpt": "Example Corp launched Product One for customers in 2026.",
      "confidence": "high",
      "status": "verified"
    }
  ]
}
```

Required evidence fields:

- `entity`: exact value from `target_entities`.
- `claim`: one atomic factual statement.
- `source_url`: the opened evidence page, never a search-results URL. For
  `source_type=user_input` in file-only routes, use a stable `file:` or
  `user-input:` reference with page/section context.
- `source_type`: `first_party`, `government`, `regulator`, `filing`,
  `standards_body`, `academic`, `reputable_media`, `secondary`, or
  `user_input`.
- `evidence_excerpt`: short page text that names the entity and supports the
  claim. Keep within copyright limits.
- `confidence`: `high`, `medium`, or `low`. A `verified` row cannot be `low`.
- `status`: `verified`, `conflicting`, or `unverified`.

Conflict fields:

- When a source checks a fact supplied by the user, include
  `user_input_claim` and `user_input_alignment` (`supported`, `conflicting`, or
  `unverified`).
- A conflicting row must include `conflict_note`.
- An unverified row must include `unverified_reason`.

Entity/source rules:

- Every target entity needs verified evidence.
- When an entity declares `official_domains`, it also needs at least one
  verified `first_party` row whose URL hostname matches that domain.
- `first_party` means owned by the target entity; government, regulator,
  filing, standards, or academic pages retain their own source type.
- The validator checks that claim numbers occur in the excerpt and that the
  claim and excerpt have meaningful lexical overlap. This is a hard
  claim-to-excerpt gate; the researcher remains responsible for opening the
  page and copying the excerpt faithfully.
- Conflicting and unverified rows are retained for disclosure but excluded from
  `verified_evidence` in the machine-readable report.

### Validation Report

After the Markdown artifacts are complete, run the bundled validator with
`--report {workspace}/research/qa/{topic}_research_check.json`. The report is
the machine-readable handoff to downstream presentation/report workflows and
contains `ok`, route, topic, actual/minimum dimension counts, checked files,
issues, warnings, evidence counts, first-party coverage, and the
`verified_evidence` array. Each verified row includes a canonical
`entity | claim | source_type | source_url` string for downstream fact binding.
Do not create this JSON by hand. If any checked research file or the evidence
ledger changes, rerun the validator so the report is newer than its inputs.

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
