---
name: pptx
description: Create, inspect, edit, validate, render, and QA PowerPoint decks. Use when the user mentions PowerPoint, PPT, PPTX, slide deck, presentation, template slides, speaker notes, slide images, or asks to read, generate, create, make, design, or modify a .pptx artifact. New decks default to HTML-first editable export through the bundled `dom-to-pptx` exporter.
keywords: [ppt, pptx, slide, slides, deck, presentation, powerpoint, 幻灯片, 演示文稿, 投影片, 路演, BP, 提案, 路演ppt]
---

# PPTX Skill

Use this skill whenever a PowerPoint deck is an input, output, or deliverable.

## 0. Non-negotiable Rules

1. New deck tasks use HTML-first editable generation by default.
2. Existing PPTX/template edits preserve the original PPTX structure.
3. `python-pptx` must not create a new deck.
4. Do not silently downgrade generation mode.
5. Visual QA via rendering is optional, not required. See §4.2 for triggers.
6. If render is attempted but blocked (missing `soffice`/PDF renderer), continue without it; do not treat it as a delivery blocker.
8. Before writing any slide HTML, invoke the `html-templates` skill to fetch the Visual DNA profile (palette / typography / decoration tokens). See §3.0. This applies to every new HTML-first deck without exception.
7. `.slide` must be exactly `1920px × 1080px` (16:9). **Do not author these dimensions from memory** — copy `references/starter/common.css` to `drafts/common.css` and use its `.slide` block verbatim. `html_self_check.js` and `html_to_editable_pptx.js` hard-assert this exact size against **every** slide (not auto-detected from slide 1), so 1280×720 / 1400×840 / 1600×900 / viewport units / scaled wrappers all fail. **Do not pass `--width`/`--height`** — those flags are rejected. For a deliberately non-standard deck the user must opt in: pass `--canvas WxH` to **both** scripts and set the same `WxH` in the `.slide` CSS. Mismatched dimensions are a hard failure, not a fixable warning.
9. **Never re-serialize a whole multi-slide deck through a single `write_file` call.** Writing every slide's HTML in one tool call routinely overruns the provider output-token limit and the call is truncated mid-stream (`finish_reason=length`), losing the entire turn. For decks of 6+ slides, author per-range fragment files and merge them (see §3.4). When you already hold sub-agent drafts, the orchestrator merges them with `merge_html_fragments.js` — it must not paste their combined content back into one `write_file`.
10. Any PPTX line geometry written by direct generation paths (`PptxGenJS` / OOXML / python-pptx / other direct generators, i.e., not `dom-to-pptx` HTML export) must avoid negative width/height. Normalize line geometry from start/end coordinates (`x1`,`y1`,`x2`,`y2`) into non-negative geometry before writing geometry boxes: `x=min(x1,x2)`, `y=min(y1,y2)`, `w=abs(x2-x1)`, `h=abs(y2-y1)`.
11. When the task declares `creative_image_mode`, successful image generation is mandatory: at least one `generate_image` call must complete and the generated asset must be referenced in `assets/generated/manifest.json`. If `generate_image` is unavailable or every call fails, mark the deck as blocked and do not present the PPT as completed.
12. New decks pass the content & outline gate before any HTML or image work (§1.1). A slide plan is the prerequisite for authoring slides. When the request is under-specified or under-sourced, **reject warmly, not coldly**: ask the user a focused clarifying question, or route the topic to `research-synthesis` — never fabricate facts and never write a flat refusal. (Hard `BLOCKED` is reserved for the `creative_image_mode` image rule above.)

## 1. Route Decision

### New deck

Use this path by default:

1. **Pass the content & outline gate first (see §1.1 and `references/outline.md`).** Do not write any slide HTML — and do not start image planning — until a slide plan exists whose page-level content is either supplied by the user, carried over from an upstream expert/research step, or grounded by `research-synthesis`. If the material is too thin to build a faithful deck, do not fabricate and do not cold-reject — **ask the user one focused question, or route to `research-synthesis`** (§1.1).
2. invoke the `html-templates` skill to fetch the Visual DNA profile (see §3.0)
3. plan slide-level image decisions in `assets/generated/manifest.json`; record the whole deck theme in `deck_context`, and when the image service is available, covers, dividers, campaign/launch/vision pages, and abstract concept pages should normally choose `generate`. Investor pitch decks, product launch decks, and premium B2B SaaS-style decks with explicit visual direction (for example "VC", "融资路演", "高端", "贵气", "靠谱", "发布会", "深色背景") are strong visual-asset briefs: use `generate` for at least the cover and one solution/product/vision hero slide unless the user opts out or the image service is unavailable.
4. call `generate_image` for every `generate` item before writing final slide HTML
5. for data charts, keep the source dataset/chart spec and use ECharts as the HTML preview for chart pages; final PPT must preserve chart data through native PowerPoint chart/table output, not through screenshots. If a chart/table dataset is written under `assets/data/*.json`, `deck.html` must reference it from a `data-pptx-chart` root with `data-chart-spec-src` (or embed the same recoverable spec with `data-chart-spec`); do not write a separate static SVG/bar layout with copied numbers.
6. create the slide HTML using the slide plan, Visual DNA profile, and generated local assets as hard constraints. For decks with **6 or more slides** (or dense source material / likely-large HTML), you **must** use the fragment-drafting workflow in §3.4 — author per-range draft files and combine them with `merge_html_fragments.js`. Smaller decks may write `deck.html` directly in one pass.
7. when `assets/generated/manifest.json` contains `layout_contract`, run image layout contract validation
8. when `assets/generated/manifest.json` declares `creative_image_mode`, run image manifest validation before HTML self-check
9. run HTML self-check
10. export with `scripts/html_to_editable_pptx.js`
11. run structural QA (package validation, text extraction, placeholder scan)
12. render and inspect only if §4.2 triggers apply

### 1.1 Content & outline gate (new decks)

The deck's page-level content is decided **before** layout and images. The skill
owns the *slide plan* (page → message → layout intent → visual), not deep
research. Run this gate at the start of every new deck:

1. **Enough content already?** If the user (or an upstream expert/research step)
   already supplied page-by-page content — titles, order, key points, data —
   treat that as the source of truth, build/confirm the slide plan per
   `references/outline.md`, and continue. This is the common case; do not invent
   a new storyline over usable input.
2. **Only structure is unclear?** If the *facts* are available but the framing is
   ambiguous (audience, page count, ordering, what to emphasise, plan-vs-build),
   **ask back** — one to three focused questions, and where reasonable propose a
   sensible default so the user can just confirm. Do not silently guess a whole
   narrative, and do not stall with an open-ended "tell me more".
3. **Topic needs facts you don't have?** If the deck needs evidence, market/
   industry/company/policy data, or claims that must be sourced, and the material
   is thin or absent, **do not fabricate and do not write a cold rejection.**
   Hand off to research first:

   ```
   Skill(skill="research-synthesis",
         args="<the deck topic + what facts/evidence the slides need>")
   ```

   Then build the slide plan from the returned, sourced findings. If
   `research-synthesis` is unavailable in this session, say so and ask the user to
   provide the source material, rather than presenting unsourced content as fact.

Reserve a hard `BLOCKED` for the `creative_image_mode` image requirement (§0
rule 11) — a normal deck that is merely under-specified is handled by asking back
or routing to research, never by a flat refusal. Mark assumed or illustrative
figures as such in the slide plan's `evidence`/`notes`; never imply fabricated
data is sourced.

**`creative_image_mode` carve-out:** in `creative_image_mode` a short topic (e.g.
"茉莉花茶制作过程") is a *creative brief* — expand it imaginatively into a visual
storyline; do **not** route it to `research-synthesis` or stall on questions
unless the user explicitly wants sourced facts/figures. Branch 3 above applies to
fact/evidence-driven decks, not creative/atmospheric ones.

### `creative_image_mode`

This mode is activated when the user explicitly asks for a creative/image-rich PPT, when an upstream expert/team instruction says `creative_image_mode`, or when the "Creative PPT / image-generation PPT" expert/team is selected.

Do not require the literal words `creative_image_mode` when the user's brief clearly asks for a polished, visual, pitch-style deck. A VC/investor pitch, launch, brand, or premium B2B SaaS deck with explicit art direction should be treated as image-generation-expected even if the user only says "图", "视觉", "高端", "贵气", "靠谱", "发布会感", "深色背景", or similar. Data charts remain editable charts/tables; the generated images are for hero visuals, product mockups, atmosphere, transformation metaphors, and controlled backgrounds.

Mode contract:

1. Treat the user input as a PPT creation brief even if it is only a short topic such as "茉莉花茶制作过程".
2. The deck must include generated bitmap visuals. At minimum, the cover must use `decision: "generate"` and a successful `generate_image` output under `assets/generated/`.
3. Prefer `generate` for cover, section divider, process hero, atmosphere/scene, poster-like, and closing slides. Dense data/table/process detail slides may use editable HTML/CSS/SVG, but they do not satisfy the mandatory generated-image requirement unless at least one other slide generated an asset.
4. If using full-slide or background generated images, create `layout_contract` before writing the prompt and keep text regions calm, low-detail, and low-contrast. Do not make the non-focus side look empty; extend the scene with faint texture, atmospheric shapes, or soft background motifs that support the theme without competing with text.
5. If `generate_image` is not configured or fails for all required images, stop before claiming completion. Return `BLOCKED: creative_image_mode requires generated images`, include the failure reason, the image plan, and any draft HTML/outline paths. Do not silently downgrade to a normal text-only PPT or a pure HTML-shape deck.
6. Final delivery must list generated asset paths and the manifest path. If there are zero successful generated assets, the final status is blocked, not completed.

If browser host preflight blocks HTML export, ask the user to choose one route:

1. `HTML`: deliver `deck.html` first, export later after host setup
2. `PPTX`: switch to native `PptxGenJS`

### Existing deck or template

Use this path for edits:

1. copy original deck
2. extract text
3. apply edits
4. validate package
5. render and inspect only if §4.2 triggers apply

### Native `PptxGenJS`

Use only when the user clearly requires it:

1. native PowerPoint charts/tables are required
2. user requires PowerPoint-native structure
3. HTML-first is impossible and user accepts the tradeoff

Do not switch routes based on convenience.

## 2. Minimal Commands

| Task | Command |
|---|---|
| Validate outline | `${BOX_AGENT_NODE:-node} scripts/validate_outline.js outline.json` |
| Extract text | `${BOX_AGENT_PYTHON:-python3} scripts/extract_text.py input.pptx` |
| Validate package | `${BOX_AGENT_PYTHON:-python3} scripts/validate_pptx_package.py input.pptx` |
| Render PPTX | `${BOX_AGENT_PYTHON:-python3} scripts/render_pptx.py input.pptx --out rendered` |
| Validate image manifest | `${BOX_AGENT_NODE:-node} scripts/validate_image_manifest.js assets/generated/manifest.json --mode creative_image_mode --min-generated 1 --report qa/image_manifest.json` |
| Validate image layout contract | `${BOX_AGENT_NODE:-node} scripts/validate_image_layout_contract.js deck.html assets/generated/manifest.json --report qa/image_layout_contract.json` |
| HTML self-check | `${BOX_AGENT_NODE:-node} scripts/html_self_check.js deck.html --dom-to-pptx --allow-local-images --report qa/html_self_check.json` ⚠️ 画布固定 1920×1080，不要追加 `--width/--height`（已被拒绝）；非标准尺寸用 `--canvas WxH` |
| Export HTML | `${BOX_AGENT_NODE:-node} scripts/html_to_editable_pptx.js deck.html output.pptx` ⚠️ 画布固定 1920×1080，不要追加 `--width/--height`（已被拒绝）；非标准尺寸用 `--canvas WxH` |
| Check local deps | `${BOX_AGENT_PYTHON:-python3} scripts/setup_check.py` |
| Check HTML export env | `${BOX_AGENT_NODE:-node} scripts/check_html_export_env.js` |

⚠️ **Dependency probing**: never use bare `node -e "require.resolve('playwright')"` to check for installed packages. Box-Agent installs Node deps into the **office-raccoon managed prefix** (`~/Library/Application Support/office-raccoon/node_modules/` on macOS, `$APPDATA/office-raccoon/node_modules/` on Windows, `~/.config/office-raccoon/node_modules/` on Linux), which is **not** on the default `NODE_PATH`. A naked `node -e` process will report every managed package as `not found`. Always use `scripts/check_html_export_env.js` (Node) or `scripts/setup_check.py` (Python) — both look in the managed prefix.

## 3. HTML-first Requirements

### 3.0 Before generating slide HTML (mandatory)

Always invoke the `html-templates` skill first to obtain the visual style constraints for this deck:

```
Skill(skill="html-templates",
      args="<the user's original brief verbatim>")
```

That skill returns a structured Visual DNA profile (palette, typography, decoration tokens, style rules). Treat its output as **hard constraints** when writing the HTML. Do not generate slide HTML without running this step — model defaults to "stay in the current skill" and will not auto-route to `html-templates` unless explicitly called from here.

If `html-templates` is unavailable in this session, fall back to authoring the deck with the existing palette/typography conventions and note the absence in `Limitations`.

### 3.1 Layout constraints

1. `.slide` must be exactly `1920px × 1080px` — copy `references/starter/common.css` rather than authoring the dimensions (see §0 rule 7; `--width/--height` are rejected, use `--canvas WxH` only for an opt-in non-standard deck).
2. Leave 16-24px text slack to reduce PowerPoint wrap drift.
3. For top/middle/bottom layouts, center the main content group in the available middle area. Do not build slides by stacking blocks from the top with repeated `margin-top`; compute the content group's height and balance top/bottom whitespace with flex/grid alignment or explicit `top` values.
4. Use relative asset paths.
5. Do not inline large images as data URLs.
6. Every slide must record an explicit image decision in `assets/generated/manifest.json`; each `generate` prompt must include the whole deck theme/context before the slide-specific visual subject. Covers, dividers, posters, campaign/launch/vision pages, abstract concept pages, investor-pitch/product-demo hero pages, premium B2B SaaS pages, and emotionally led closing pages must use `generate` via the `generate_image` tool unless the user opts out, the image service is unavailable, or a real/source-backed asset is required.
7. ECharts/canvas charts are allowed only as HTML preview surfaces backed by `data-pptx-chart` and recoverable chart data. They must not be baked into `assets/bg-capture/*.png` or delivered as screenshot-only chart images when the data is available.
8. Keep page numbers on non-cover slides consistent with slide order.
9. Read `references/html-first.md` and `references/html-editable.md`.
10. Keep image generation rules in `references/image-assets.md`.
11. For generated full-slide/background slides, text-bearing HTML elements that correspond to `layout_contract.text_regions` must carry `data-layout-region="<region name>"`, and `scripts/validate_image_layout_contract.js` must pass before HTML self-check. Small/medium hero images in fixed frames do not require this contract unless they overlap text-safe areas.
12. In `creative_image_mode`, `assets/generated/manifest.json` must include `"mode": "creative_image_mode"` and at least one image-plan entry with `decision: "generate"`, `status: "generated"` (or equivalent success marker), and an existing `output_path`.

### 3.2 Data charts and ECharts previews

For data presentation slides, preserve data first:

1. When a slide contains quantities, rankings, comparisons, trends, proportions, KPIs, financials, market sizing, benchmark results, time-series data, or operational metrics, prefer a visible data display by default: native table, KPI strip, bar/line/area/pie chart, matrix, comparison table, or mini-dashboard. Use plain bullets only when the data is too sparse or the user explicitly asks for text-only slides.
2. Store chart/table data in `assets/data/*.json` or an equivalent local source file.
3. In `deck.html`, use ECharts for browser preview and layout tuning when the slide is chart-led or backed by `assets/data/*.json`. The chart root must be marked with `data-pptx-chart` and must reference or embed a chart spec via `data-chart-spec`, `data-chart-spec-src`, or a child `<script type="application/json" data-chart-spec>`. If a dataset exists in `assets/data/`, do not duplicate the numbers into static SVG, absolute-positioned bars, or text-only chart markup without linking the dataset.
4. When creating the final PPTX, convert available chart data to native PowerPoint charts/tables whenever the recipient may edit numbers. Do not flatten an ECharts canvas/SVG into a screenshot just because it looks correct in HTML.
5. If native chart conversion is unavailable, report the chart export as `BLOCKED` or switch to the confirmed native `PptxGenJS` chart route; do not silently deliver screenshot-only chart images.

### 3.3 Visual effects scope (decoration vs text-bearing)

`html_to_editable_pptx.js` runs `bg_capture` by default (`--bg-capture always`). It screenshots every **decoration node** into a slide-level bitmap and then removes it from the export tree, so any CSS effect on a decoration node ends up as pixels — not as a live PPTX shape. The dom-to-pptx blacklist applies **only to elements that survive capture**. ECharts/canvas chart nodes marked with `data-pptx-chart` are not decoration nodes and must stay out of the background screenshot path.

**Decoration nodes (free to use any visual effect):**
- Empty `<div>` (no text inside, no `<img>` inside)
- `<svg>`, `<hr>`, `<canvas>`
- Anything nested inside an `<svg>`

**Allowed on decoration nodes and on `.slide` background:**
`transform`, `clip-path`, `text-shadow`, `backdrop-filter`, `mix-blend-mode`, `animation`, `transition`, `radial-gradient`, `conic-gradient`, `filter: drop-shadow/brightness/contrast/saturate/hue-rotate/...`.

**Still forbidden everywhere (bg_capture does not fix these):**
- Viewport units `vh/vw/vmin/vmax` — these are layout sizes, not visual effects
- `<video>`, `<audio>`, `<iframe>` — not captured at all
- Non-absolute / non-data / non-file `<img>` src on text path
- `position: static` or `overflow: visible` on `.slide`

**Still forbidden on text-bearing elements** (these survive capture as live PPTX shapes):
- `transform`, `text-shadow`, `clip-path`, `backdrop-filter`, `mix-blend-mode`, `animation`, `transition`, `radial-gradient`, `conic-gradient`, non-blur `filter`

**Practical guidance:**
- Want a glowing pill, gradient orb, blurred halo, rotated badge? Put it in an empty `<div>` (or SVG), then place the text in a **separate** sibling element on top. The decoration goes into the bitmap; the text stays sharp and editable.
- `.slide`'s own `background` can be any gradient / image / blend — it ends up in the bitmap layer.
- If `html_self_check.js` flags a visual effect on a "text-bearing element", the fix is usually to split the element: one decoration sibling for the effect, one text element for the words.

### 3.4 Fragment drafting (large decks — mandatory for 6+ slides)

A full multi-slide deck's HTML is large. Emitting it through a single
`write_file` call routinely exceeds the provider's output-token limit, so the
call is truncated mid-stream (`finish_reason=length`) and the whole turn is
lost. Avoid this by authoring the deck in fragments and merging them with a
script — the model never has to stream the entire deck in one tool call.

**Workflow:**

1. Copy `references/starter/common.css` to `drafts/common.css` — it already
   contains the locked `.slide` 1920×1080 frame. Add the deck's shared CSS
   (palette variables, typography, reusable component classes) into this same
   file **once**; do not edit the `.slide` width/height/position/overflow, and do
   not repeat styles inline on every slide — define a class in `common.css` and
   reference it.
2. Author each contiguous slide range into its own draft file, e.g.
   `drafts/slides_01_04.html`, `drafts/slides_05_08.html`,
   `drafts/slides_09_12.html`. Each draft contains **only**
   `<section class="slide" data-slide="NN">…</section>` blocks for its range —
   no `<html>`, `<head>`, `<body>`, `<style>`, or `<script>` wrapper.
   - **Every section MUST carry a numeric `data-slide`** (`merge_html_fragments.js`
     rejects any section without one). Number them **`01`, `02`, …` continuously
     from `01` across the whole deck** (not per-fragment) — the merge enforces a
     gap-free, non-duplicated `01..N` sequence and sorts by `data-slide`, so the
     fragment file order on the command line does not matter. Example:
     ```html
     <section class="slide" data-slide="05">…</section>
     <section class="slide" data-slide="06">…</section>
     ```
   - **Charts inside a fragment must use the `data-chart-spec` or
     `data-chart-spec-src` attribute form** (see §3.2) — the inline
     `<script type="application/json" data-chart-spec>` variant is **forbidden in
     fragments** because the merge strips/rejects any `<script>`. Put the spec in
     an attribute, or reference an external `assets/data/*.json` via
     `data-chart-spec-src`.
3. Keep each fragment small enough to write comfortably in one `write_file`
   call (roughly ≤4 slides per fragment, fewer if a slide is dense). When in
   doubt, split further.
4. Merge into the final single-file `deck.html`:

   ```bash
   ${BOX_AGENT_NODE:-node} "$PPTX_SKILL_DIR/scripts/merge_html_fragments.js" \
     --css drafts/common.css \
     --out deck.html \
     --title "Deck title" \
     drafts/slides_01_04.html drafts/slides_05_08.html drafts/slides_09_12.html
   ```

5. Continue with HTML self-check and export on the merged `deck.html` as usual.

**When sub-agents drafted the slides:** each sub-agent writes its own fragment
file directly (`drafts/slides_NN_MM.html`). The orchestrator then **only runs
the merge command** above. It must **never** read the drafts back and paste
their combined content into a single `write_file` — that recreates the exact
truncation failure this workflow exists to prevent.

## 4. QA Gates

Required for every created or modified deck:

1. package validation
2. text extraction
3. placeholder scan
4. slide count and order check

For HTML-first, `qa/html_self_check.json` must exist before export.
Fix self-check **issues** and retry up to 3 times. Self-check **warnings** never
block export — record them in `Limitations` and move on; do not spend repair
rounds on warnings.
**Convergence cap (hard rule):** if the same issue set persists — or stops
shrinking — after 3 repair rounds, STOP. Export with `--allow-self-check-issues`
and record the residual issues in `Limitations`. Do **not** edit the same node a
4th time, and never loop edit -> recheck on overflow/cosmetic nits — a recheck
loop that fails to reduce the issue count is a failure mode, not progress.
If `assets/generated/manifest.json` contains `layout_contract`, `qa/image_layout_contract.json` must exist and pass before HTML self-check.

Rendered visual inspection is **not** in the required list. See §4.2.

### 4.1 Visual issue triage

When rendered visual inspection surfaces a problem, classify it before reacting. Do **not** change route or strategy for cosmetic issues.

**Blocker — must fix:**
- Content extending outside the slide bounds, or a large overflow (>64px) that
  breaks the layout — self-check reports these as `issues`
- Image failed to load, broken asset references
- Wrong slide order, missing pages, misaligned page numbers
- Layout collapse (overlapping blocks, zero-size containers)
- Typos in user-supplied copy, factual errors
- dom-to-pptx drift that hides a whole element

**Cosmetic — accept and move on:**
- Minor text overflow within the authored slack (≤64px) — self-check reports
  these as `warnings`, not `issues`; they do not block export
- Watermark / signature artifacts on generated images
- A single line wrap on a long title or trailing punctuation
- Minor kerning / leading drift after dom-to-pptx export
- Color shifts within the same palette family
- Subpixel alignment between adjacent blocks

**Forbidden reactions to cosmetic issues:**
- Switching `generate` → `draw_in_html` / pure vector / icons
- Switching HTML-first → `PptxGenJS` or `python-pptx`
- Abandoning the image plan and rewriting slides text-only
- Cascading "re-check after fix" loops that surface new cosmetic nits

Cosmetic issues go directly into the `Limitations` section. They do not block delivery, do not justify a route switch, and do not get a repair attempt.

### 4.2 Visual inspection is optional

Rendered visual inspection (`scripts/render_pptx.py` + reading the resulting images) is **opt-in**, not a required gate.

**Default behavior:** skip visual inspection. Structural QA (package validation, text extraction, placeholder scan, slide count) is sufficient for delivery. Do not call `render_pptx.py` for visual judgment on every deck.

**Trigger visual inspection only when:**
1. The user explicitly asks to see / review / render the deck.
2. A blocker-class issue is already suspected from structural QA (e.g. text-extract shows truncated content) and visual confirmation is needed to locate the failure.

**When visual inspection runs:**
1. One pass only. Classify findings per §4.1.
2. Fix blockers, accept cosmetics, report.
3. Do **not** re-render after the fix to verify cosmetics. Re-render only if the fix targeted a blocker.
4. Do **not** trigger a second visual pass to "double-check" your own judgment.

Rendering for the user's own preview (so they can open the PNGs) is fine and does not count as visual QA — just generate the images, do not narrate findings or self-critique.

## 5. Office Raccoon Runtime

Read this order first:

1. `references/runtime-office-raccoon.md`
2. `references/dependency-policy.md`
3. `references/shell-safety.md`

Use managed variables for all commands:

1. `$BOX_AGENT_NODE`, `$BOX_AGENT_PYTHON`, `$BOX_AGENT_NPM`
2. `$BOX_AGENT_RENDER_RUNTIME`, `$BOX_AGENT_SOFFICE`, `$BOX_AGENT_PDFTOPPM`
3. `$BOX_AGENT_RUNTIME_PREFIX`

Install only into managed Office Raccoon prefixes.
No global, Homebrew, or system-wide installs without explicit approval.
No `/tmp`, no `>/tmp`, and no writes outside workspace/output folder.

## 6. Final Response Format

Use exact sections in this order:

1. `Created`
2. `Source`
3. `QA`
4. `Fixes`
5. `Limitations`

If a QA step is blocked, write `BLOCKED` for that step.

## 7. References

1. `references/outline.md`
2. `references/html-first.md`
3. `references/html-editable.md`
4. `references/pptxgenjs.md`
5. `references/ooxml-editing.md`
6. `references/qa.md`
7. `references/api-integration.md`
8. `references/runtime-office-raccoon.md`
9. `references/dependency-policy.md`
10. `references/shell-safety.md`
11. `references/image-assets.md`

## 8. Mode lock and fallback

1. Lock the chosen route after preflight and explicit user confirmation.
2. Do not switch from HTML-first to `PptxGenJS` to speed up completion.
3. Do not switch to `python-pptx` for new deck creation.
4. If preflight or host checks change while running, restart from current source with the new route decision.
5. Keep report language explicit: `export blocked`, `render blocked`, `dependency blocked`, `mode locked`.

## 9. Compatibility baseline

1. Support macOS, Linux, and Windows for this skill.
2. Use managed runtime binaries first, then fallback checks.
3. Keep generated files inside workspace or requested output folder.
4. Prefer editable PPTX and source files over packaged archive delivery unless requested.
5. Keep output deterministic for reruns.
