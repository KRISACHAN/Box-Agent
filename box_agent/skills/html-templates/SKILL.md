---
name: html-templates
description: Use when generating HTML pages, slide decks, posters, or reports that should adopt a specific visual style — whether invoked directly by the user OR called by another skill (e.g. pptx, poster, report skills) that has already decided the structure but needs to pick and apply a visual identity. Matches the brief's mood / industry / density against 32 pre-extracted design "Visual DNA" profiles, then injects the chosen profile's color, typography, and decoration rules as hard constraints into the generation prompt. The caller writes HTML inside their own structural conventions; this skill only governs the look.
keywords: [html, template, visual, mood, style, identity, 模板, 网页风格, 视觉风格, 网页设计]
---

# HTML Templates — Visual DNA Library

A style-constraint library. Match the user's request to one of 32 pre-analyzed design profiles, then write fresh HTML that obeys that profile's color, typography, and decoration rules — inside whatever HTML structure the user has already specified.

## Asset

`references/visual_dna.json` — the only file you read. Each of the 32 entries contains:

- `profile` — `industry_fit`, `mood_tone`, `visual_density`
- `color_palette` — `bg_main`, `text_main`, `accent`, `muted` (named hex)
- `style_rules_text` — 150-250 字中文铁律，描述性而非像素级（保留 hex、em、%、fr、unitless 数值与 CSS 关键字；不含 px / vw / vh / clamp 等画布相关数值）
- `typography` — font families, weights, role-based size labels, letter-spacing, line-height
- `decoration_tokens` — 3-6 named classes, each described by its visual role + CSS keywords (no pixel values)

## Workflow

Every request maps to exactly one template. Never refuse to match. Never ask the user to choose between candidates — pick the top-1 and proceed.

### 1. Extract

Before reading the JSON, distill the user's brief into a structured signal block. Infer aggressively when the user didn't say something explicitly — a "周报模板" implies medium-high density and quiet formality even if the user never used those words.

```
intent:          deck | poster | report | landing | dashboard | one-pager
subject:         <one phrase: what is the artifact about>
audience:        投资人 | 客户 | 同事 | 社区 | 公众 | 学术 | 自己
mood_signals:    [<adjectives, extracted or inferred: 克制/活泼/复古/学术/...>]
industry_signals:[<科技/金融/艺术/教育/时尚/游戏/出版/...>]
density_hint:    Low | Medium-Low | Medium | Medium-High | High
scheme_hint:     dark | light | warm | cool | <none>
color_hint:      [<specific colors the user named, if any>]
formality:       low | medium | high
```

Keep this extraction internal — do not surface it to the user.

For business, product, launch, scenario-demo, consulting, board, investor,
training, enterprise enablement, or implementation decks, infer
`density_hint: Medium-High` by default. Use `Low` or `Medium-Low` only when the
user explicitly asks for sparse, cinematic, manifesto, quote-led, gallery-like,
or atmospheric slides. A dark/tech/launch mood is not by itself a reason to
choose a low-density template; the deck still needs enough visible structure to
carry the message.

### 2. Match

Read `references/visual_dna.json` and score every one of the 32 entries against the signal block. Weights:

- mood_tone fit (semantic similarity to `mood_signals`) — **×3**
- industry_fit overlap with `industry_signals` — **×2**
- visual_density alignment with `density_hint` — **×2**
- color_palette alignment with `scheme_hint` / `color_hint` — **×1**
- formality fit (inferred from mood_tone + industry_fit) — **×1**

Pick the highest-scoring entry. Ties broken by mood_tone, then by industry_fit, then alphabetically. State the chosen `template_id` and one sentence on why it won — then proceed without asking.

### 3. Inject

Treat the chosen entry's fields as **hard constraints**:

- `color_palette` — these are the only colors allowed. No drift.
- `style_rules_text` — every qualitative rule (粗/细、紧凑/宽松、对称/错位、圆角形态、网格比例) must be honored. The DNA is canvas-agnostic; you choose the absolute pixel/rem values that fit the user's canvas while preserving the described proportions and contrasts.
- `typography` — font families, weights, role-based sizing intent, letter-spacing, line-height are non-negotiable. Translate role labels (display 巨大 / 正文级 / 标签级 etc.) into concrete sizes consistent with the canvas.
- `decoration_tokens` — class names + described CSS are the vocabulary for cards, labels, dividers, etc. Reuse the token names verbatim so the visual identity stays coherent.

Do not soften these into suggestions. The output should be visually indistinguishable from a slide in the source template, even though no template code was copied.

### 4. Compose

Write the HTML using **the user's structural conventions** (their canvas size, wrapper classes, build pipeline, semantic patterns). Apply the visual DNA *inside* that structure.

**Conflict resolution:**

- User's structural conventions > visual DNA visual rules — always.
- If the user specifies a layout primitive that contradicts the template's decoration vocabulary, keep the user's primitive but restyle it with the template's CSS values.
- If the user has not specified something (e.g. how cards should look), the visual DNA fills the gap.

### 5. Verify

Before reporting done:

- Every color in the output appears in `color_palette` (or is a documented variant like opacity adjustment).
- Type families, weights, and size ranges match `typography`.
- At least 2-3 `decoration_tokens` are actually used; otherwise the output looks generic.

## When to Extend vs. Restart

- New section in the same artifact → reuse the same profile. Never switch templates mid-artifact.
- Separate artifact → re-run Match from scratch.
- Missing component (timeline, comparison table, etc.) → design a new one using the same color, type, spacing, and border vocabulary so it looks like it belongs in the same family.

## Anti-patterns

- Mixing two profiles in one artifact. Pick one.
- Treating `style_rules_text` as inspiration. It is a spec.
- Inventing class names. Use the names in `decoration_tokens` so the user can recognize the vocabulary across artifacts.

## Attribution

Visual DNA was distilled from [`zarazhangrui/beautiful-html-templates`](https://github.com/zarazhangrui/beautiful-html-templates) (MIT, © 2026 Zara Zhang). The original license is preserved at `references/UPSTREAM_LICENSE`.
