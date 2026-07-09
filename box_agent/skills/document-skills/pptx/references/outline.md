# PPTX Outline Planning

Use this planning stage only when it improves the deck. Do not turn every prompt
into a new invented storyline. If the user already provides enough page-by-page
content, order, titles, data, or structure, treat that prompt as the outline and
move directly to `deck.html` after a light mapping/consistency check.

The goal is to make the storyline, per-slide message, visual intent, and
evidence explicit before visual layout starts without overriding user intent.

## Decision Gate

Create `outline.json` by default for any new deck request. The bar for
skipping the outline is high: only skip when the user's prompt already
contains a page-by-page breakdown with titles, content, and order that can
be mapped directly to `deck.html` without structural judgment.

Typical cases that benefit from an outline:

- The user gives only a broad topic, goal, or document type.
- The user provides partial structure (some titles, some content) that needs
  gap-filling, reordering, or evidence-to-slide mapping.
- The deck is narrative-heavy (BP, strategy, consulting, research,
  investment, product launch, annual review, data-story, etc.).
- Page count, slide order, audience, evidence, or key claims are unclear.
- The prompt asks for "帮我规划", "大纲", "结构", "storyline", or equivalent.

Only skip the outline when **all** of these are true:

- The user already specifies every page with title, content, and order.
- The structure is complete enough to write `deck.html` directly.
- No grouping, prioritization, or narrative arc decisions are needed.

## When the request is under-specified or under-sourced

A new deck must not start from too little. But "too little" is never answered
with a cold refusal — it is answered by **asking back** or **routing to
research**. Pick the branch that fits:

1. **Content is sufficient.** The user or an upstream expert/research step
   already gave usable page-level material (titles, order, key points, data).
   Treat it as the source of truth and build the outline. Do not invent a
   competing storyline over usable input.

2. **Only the structure/framing is unclear** (facts are available, but audience,
   page count, ordering, emphasis, or plan-vs-build is ambiguous). **Ask back** —
   one to three focused questions, and where reasonable offer a sensible default
   the user can simply confirm. Examples:
   - "这套面向投资人还是内部评审?大概几页?" (then propose a default count)
   - "你已有这些要点,我按 问题→方案→市场→进展 的顺序排,可以吗?"
   Do not stall with an open-ended "tell me more", and do not silently guess an
   entire narrative the user never asked for.

3. **The topic needs facts you don't have** (claims, market/industry/company/
   policy data, anything that must be sourced) and the material is thin or
   absent. **Do not fabricate, and do not write a flat rejection.** Route to
   research first, then build the outline from the sourced findings:

   ```
   Skill(skill="research-synthesis",
         args="<the deck topic + exactly what facts/evidence the slides need>")
   ```

   If `research-synthesis` is unavailable in this session, say so plainly and ask
   the user to supply the source material — never present unsourced content as
   fact. Keep the boundary clear: this skill turns researched/supplied content
   into a slide plan; it does not itself perform deep research, fact-checking, or
   source-credibility judgement.

Reserve a hard `BLOCKED` for the `creative_image_mode` image requirement only. A
normal deck that is merely under-specified is handled by asking back or routing
to research — warmly, with a concrete next step — never by a cold "I can't do
this".

## Required Output

When the decision gate says an outline is needed, create an `outline.json`
beside the future `deck.html`:

```json
{
  "deck_goal": "What this deck must achieve",
  "audience": "Who will read or hear it",
  "tone": "Visual and narrative tone",
  "storyline": "One-sentence narrative arc",
  "slides": [
    {
      "page": 1,
      "title": "Slide title",
      "message": "One core claim this slide proves",
      "bullets": [
        "3-5 concise points that support the message",
        "Each point should be a fact, argument, or data highlight",
        "Keep bullets parallel in structure and length"
      ],
      "layout": "cover | section | comparison | dashboard | timeline | matrix | chart | cards | closing",
      "visual": "Main chart/card/composition to build",
      "evidence": ["Data source, user-provided fact, assumption, or empty array for non-evidence slides"],
      "notes": "Speaker intent, caveats, or source assumptions"
    }
  ]
}
```

Keep this as a planning artifact. Do not put CSS, HTML, or PowerPoint object
details into `outline.json`.

## Generation Steps

1. Restate the user request as a deck goal, audience, and decision/action the
   deck should drive. Stay within facts supplied by the user or clearly marked
   assumptions.
2. Pick a storyline arc before listing slides only when the user did not already
   provide a clear order. Examples:
   - BP: problem -> solution -> product -> market -> traction -> business model
     -> competition -> team -> financing ask.
   - Strategy report: context -> diagnosis -> options -> recommendation ->
     roadmap -> risks -> next steps.
   - Analysis deck: question -> data -> findings -> implications ->
     recommendations.
3. Draft one slide per narrative beat, or map directly from the user's supplied
   page list. Each slide must have exactly one core `message`.
4. Bind evidence to every analytical, chart, market, traction, or financial
   slide. If evidence is assumed or illustrative, say so in `evidence` or
   `notes`; do not imply fabricated data is sourced.
5. Choose the intended `layout` and `visual` for each slide before writing HTML.
   When a slide contains quantities, rankings, trends, proportions, KPIs,
   market sizing, financials, benchmarks, or operational metrics, the `visual`
   should normally name a concrete data display such as `KPI strip`, `bar
   chart`, `line chart`, `matrix`, `comparison table`, `heatmap`, or
   `mini-dashboard`, not just `cards` or `text layout`. For scenario,
   use-case, capability, or demo pages, a plain `cards` layout is acceptable only
   when the cards are content-rich. If each card has just a title and 1-2 short
   lines, the `visual` must name a second layer such as a demo flow, journey
   line, role swimlane, before/after comparison, KPI strip, icon/owner row, or
   capability matrix.
6. Run `scripts/validate_outline.js outline.json` and fix failures before
   creating `deck.html`.

## Quality Bar

- Every slide has one job. If a slide has two unrelated claims, split it.
- Titles should be short and presentation-ready.
- `message` should be a claim, not a topic label. Prefer "AI cuts manual QC
  scheduling from hours to minutes" over "Product overview".
- `bullets` should have 2-5 items; each supports `message` and maps to
  distinct content on the slide. Avoid restating the title.
- Avoid repetitive slides with the same title, message, layout, or visual.
- Avoid sparse content slides that leave the lower half of the canvas empty.
  Divider, cover, quote, and cinematic pause slides may use intentional
  whitespace; normal business/product/demo/training slides should turn spare
  space into a chart, flow, matrix, process schematic, role lane, or other
  message-bearing visual.
- Use a section-divider slide only when it helps pacing.
- Put source assumptions in `evidence` or `notes`; do not hide missing data.
- For data-heavy slides, prefer chart/table/KPI/dashboard visuals over plain
  bullet lists unless the data is too sparse or text-only output was requested.
- Keep page numbers consecutive and aligned with the final slide count.

## Validation

Run:

```bash
${BOX_AGENT_NODE:-node} scripts/validate_outline.js outline.json
```

The validator checks structure, required fields, page numbering, obvious
duplicates, overlong titles/messages, missing evidence on data-heavy slides, and
basic storyline completeness. It is a hard-rule gate, not a substitute for
human/model narrative judgment.

After validation passes, use `outline.json` as the source of truth when writing
`deck.html`. The slide title, core message, visual intent, and evidence notes
should trace back to the outline. If no separate outline was needed, trace the
same fields back to the user's prompt instead.
