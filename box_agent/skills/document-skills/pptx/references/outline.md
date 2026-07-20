# PPTX Outline Planning

Every new controlled deck writes this planning artifact before scaffolding.
Do not turn a complete user-supplied page list into a new invented storyline:
map it directly into `outline.json` and keep that pass lightweight. Broad or
partial prompts require the fuller narrative/evidence planning described below.

The goal is to make the storyline, per-slide message, visual intent, and
evidence explicit before visual layout starts without overriding user intent.

## Decision Gate

Create `outline.json` for every new controlled deck request. When the user's
prompt already contains a page-by-page breakdown with titles, content, and
order, preserve it as a direct traceability mapping rather than expanding or
reordering it.

Typical cases that benefit from an outline:

- The user gives only a broad topic, goal, or document type.
- The user provides partial structure (some titles, some content) that needs
  gap-filling, reordering, or evidence-to-slide mapping.
- The deck is narrative-heavy (BP, strategy, consulting, research,
  investment, product launch, annual review, data-story, etc.).
- Page count, slide order, audience, evidence, or key claims are unclear.
- The prompt asks for "帮我规划", "大纲", "结构", "storyline", or equivalent.

Do not create a second outline, and do not use `plan_write` as a substitute for
this artifact.

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
   one focused question with only the minimum fields, and where reasonable offer a sensible default
   the user can simply confirm. Examples:
   - "这套面向投资人还是内部评审?大概几页?" (then propose a default count)
   - "你已有这些要点,我按 问题→方案→市场→进展 的顺序排,可以吗?"
   Do not stall with an open-ended "tell me more", and do not silently guess an
   entire narrative the user never asked for.

3. **The topic needs facts you don't have** (claims, market/industry/company/
   policy data, anything that must be sourced) and the material is thin or
   absent. **Do not fabricate, and do not write a flat rejection.** Load the
   research workflow first, then build the outline from the sourced findings:

   ```
   get_skill(skill_name="research-synthesis")
   ```

   Follow the selected `research-synthesis` route's coarse-to-fine evidence
   budget and persist its research artifacts. Do not replace that workflow with
   a PPT-specific four-query scan: a one-line factual prompt still needs enough
   landscape, authority, and conflict coverage to support the slide plan. After
   the route is complete, run its bundled artifact validator with
   `--report research/qa/{topic}_research_check.json`; even a reduced sequential
   run must preserve at least three distinct dimensions. Continue only after a
   fresh successful report, then omit or mark nonessential gaps instead of
   repeating the same queries. Pass resulting factual statements to the
   scaffold with repeated `--research-fact`; reserve `--fact` for verbatim
   user/source text. Treat `AuthLevel` as a ranking hint, not proof that a result
   is authoritative. When a first-party domain is known, prefer a `site:`-
   constrained query; discard SEO-looking, mirror, or unrelated results. Every
   public-research page must have at least one evidence item, and every item
   must contain the actual http(s) URL used for that claim, preferably as
   `claim | source | URL`. Never label a source FIFA/IOC/official unless that
   returned URL belongs to the named institution. The runtime rejects evidence
   URLs that were not returned by successful search, supplied by the user, or
   read successfully through a direct browser tool in this turn. If a `site:`
   query returns no matching host, never invent the expected URL; successfully
   read a known exact first-party URL or ask once for the missing source/scope.
   A normal factual-deck request already permits research
   from public authoritative sources; do not pause later to ask for permission
   to use those sources. Ask only for a strict/private source boundary,
   unavailable required evidence, or a material conflict in sources.
   If `research-synthesis` is unavailable
   in this session, say so plainly and ask
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
beside the future `deck.json`:

For `source_mode=user_provided`, exact numeric facts in a page's `message` or
`bullets` are valid quantitative evidence for chart/KPI layout selection; keep
`evidence: []` when no external URL is needed. The URL-bearing evidence ledger
is mandatory only for public-research claims, not for facts supplied directly
by the user.

When that quantitative page is authored, labels, units, and values may occupy
separate editable KPI/chart fields. Preserve all page quantities and matching
labels, but do not repeat a long source sentence in every card or data cell.
For strict source-only briefs, omit optional explanatory copy when the user did
not supply it; reserve visible `待补充` for genuinely required missing fields.

```json
{
  "deck_goal": "What this deck must achieve",
  "audience": "Who will read or hear it",
  "source_mode": "user_provided | public_authoritative_research | creative_brief",
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
      "evidence": ["Public-research claim | source name | https://actual-source.example/page; use [] for non-evidence slides"],
      "notes": "Speaker intent, caveats, or visible assumption disclosure"
    }
  ]
}
```

Keep this as a planning artifact. Do not put CSS, HTML, or PowerPoint object
details into `outline.json`.

## Generation Steps

1. Restate the user request as a deck goal, audience, and decision/action the
   deck should drive. Stay within facts supplied by the user or clearly marked
   assumptions that the user explicitly authorized.
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
   slide. If the user authorized assumed or illustrative evidence, say so in
   `evidence` or `notes` and plan a visible `假设`/`示意` disclosure on that slide;
   do not imply fabricated data is sourced. Assumptions may fill disclosed
   illustrative metrics or scenarios, but never private identity facts such as
   a company/project name, financing round or stage, founding date, team
   member/history/size, client, award, or ranking. For a required missing
   private fact, use `待补充` and ask once when it materially blocks the deck;
   otherwise omit it.
5. Choose the intended `layout` and `visual` for each slide before selecting
   controlled layout ids and filling `deck.json`.
   These are executable semantic requirements, not disposable prompting hints:
   the scaffold copies them into `slide.outline_intent`, may normalize an
   incompatible requested layout, and final QA checks both compatibility and
   explicit counts such as “三段式”, “四条标签”, “四个里程碑”, or “四象限”.
   Write the intended geometry precisely enough that this check is meaningful.
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
   scaffolding `deck.json`.

## Quality Bar

- Every slide has one job. If a slide has two unrelated claims, split it.
- Titles should be short and presentation-ready.
- `message` should be a claim, not a topic label. Prefer "AI cuts manual QC
  scheduling from hours to minutes" over "Product overview".
- `bullets` should have 2-5 items; each supports `message` and maps to
  distinct content on the slide. Avoid restating the title.
- Avoid repetitive slides with the same title, message, layout, or visual.
- Do not reuse the same evidence as the main support for more than two pages;
  combine repetitive pages or research another distinct fact.
- For public-research decks, omit nonessential gaps instead of planning visible
  `待补充` fields. Use `待补充` only for genuinely unavailable required
  user/private inputs.
- Avoid sparse content slides that leave the lower half of the canvas empty.
  Divider, cover, quote, and cinematic pause slides may use intentional
  whitespace; normal business/product/demo/training slides should turn spare
  space into a chart, flow, matrix, process schematic, role lane, or other
  message-bearing visual.
- Use a section-divider slide only when it helps pacing.
- Put explicitly authorized assumptions in `evidence` or `notes` and disclose
  them visibly on the affected slide; do not hide missing data.
- For data-heavy slides, prefer chart/table/KPI/dashboard visuals over plain
  bullet lists unless the data is too sparse or text-only output was requested.
- Keep page numbers consecutive and aligned with the final slide count.

## Validation

Run:

```bash
${BOX_AGENT_NODE:-node} scripts/validate_outline.js outline.json --report qa/outline_check.json
```

The validator checks structure, required fields, page numbering, obvious
duplicates, overlong titles/messages, missing evidence on data-heavy slides,
page-level numeric traceability, public-research source URLs, and basic
storyline completeness. It is a hard-rule gate, not a substitute for
human/model narrative judgment.

After validation passes, pass it directly to the scaffold with
`--outline outline.json`. The scaffold writes `source_outline_page` onto every
slide and, for `public_authoritative_research`, imports each non-empty
`slides[].evidence` string into `truth_contract.research_facts`. The slide title,
core message, visual intent, and evidence notes must stay on the same numbered
page through the content patch. Compile the validated deck to `index.html`; do
not hand-author the controlled HTML.
