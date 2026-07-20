# Research Task Templates

These templates work for both native subagents and local sequential rounds.
Replace bracketed fields before dispatching or executing.

## Wide Facet

```text
Mission: Explore one broad facet of [topic].

Route: A wide search.
Agent slot: [wide NN of MM in batch K].
Facet scope: [facet name and boundaries].
Context so far: [brief landscape findings].

Search requirements:
- Use the user's language for searches unless a specific locale is required.
- Prefer primary sources, official data, academic sources, reputable media, and
  original company or government materials.
- Avoid content farms, anonymous blogs, and SEO aggregators.
- Perform varied coarse-to-fine searches; do not recycle one keyword pattern.
- Before another batch, state the uncovered evidence gap it will resolve. Do not
  retry a near-equivalent entity/fact query just because a `site:` or authority-
  ranked variant returned no results; use an exact known first-party URL or mark
  the gap unresolved.

Output path: [workspace]/research/[topic]_wide[NN].md
Output format:
- Facet
- Key findings with footnote citations
- Major players and sources
- Trends and signals
- Controversies and conflicting claims
- Recommended deep-dive areas
- Footnote definitions
```

## Dimension Deep Dive

```text
Mission: Research dimension [NN] of [topic].

Route: [A/B/C/D].
Agent slot: [dimension NN of MM in batch K].
Dimension scope: [scope].
Required angles:
- Current state
- Key evidence
- Stakeholders or affected systems
- History or context
- Tensions and counter-arguments

Context:
[relevant landscape/file findings]

Source rules:
- Route C: use only supplied file content and cite file name plus section/page.
- Route D: treat file evidence as primary and external sources as supplement.
- Search routes: prioritize primary and authoritative sources.

Output path: [workspace]/research/[topic]_dim[NN].md
Output format:
Claim: [claim with inline citation]
Source: [source name or file name]
URL: [URL or file reference]
Date: [publication date or N/A]
Excerpt: [short verbatim excerpt]
Context: [surrounding context]
Confidence: [high / medium / low]
```

## Targeted Validation

```text
Mission: Resolve or narrow one conflict from cross-verification.

Agent slot: [validation NN of MM in batch K].
Conflict:
[conflicting claims, source ids, dates, and dimensions]

Requirements:
- Find independent evidence where external search is allowed.
- Preserve all existing citations.
- If the conflict is genuine or unresolved, say so directly.

Output path: [workspace]/research/[topic]_validation[NN].md
Main-agent merge target: [workspace]/research/[topic]_cross_verification.md
```

## Final Handoff

```text
Research is complete. Do not launch additional research agents.

Use these artifacts:
- Insight file: [workspace]/research/[topic]_insight.md
- Cross-verification file: [workspace]/research/[topic]_cross_verification.md
- Dimension files: [workspace]/research/[topic]_dim01.md through [topic]_dimNN.md
- File analysis: [workspace]/research/[topic]_file_analysis.md, if present
- Wide exploration files: [workspace]/research/[topic]_wideNN.md, if present

Preserve Markdown footnotes exactly. Do not renumber, strip, or replace them.
```
