# Image and manifest policy

## 0. Creative image mode

`creative_image_mode` is the strict image-generation mode used by creative PPT experts or expert teams.

Rules:

1. The manifest must include `"mode": "creative_image_mode"`.
2. At least one slide, normally the cover, must use `decision: "generate"` and must finish with a real generated file under `assets/generated/`.
3. A generated image counts only when `generate_image` succeeds, `output_path` exists, and the final HTML/PPT references that asset.
4. If no generated image succeeds, the deck status is `blocked`; do not mark the PPT as completed and do not replace the required generated asset with `draw_in_html`, `skip`, or a decorative CSS-only visual.
5. Record failures as `decision: "blocked"` with `reason`, `tool: "generate_image"`, and the attempted prompt/slide role so the user can retry after configuration or service recovery.
6. Full-slide/background generated images must still follow the `layout_contract` rules below. Fixed-frame hero images may satisfy the mandatory generation requirement without a layout contract if they do not sit behind text.

## 1. Decision first

1. Every slide must have one explicit `image_plan` entry.
2. `image_plan.decision` must be one of `generate`, `use_existing`, `draw_in_html`, `skip`, or `blocked`.
3. Prefer `generate` when a bitmap asset would make the slide faster to understand, more memorable, or visually credible.
4. Do not use `skip` as the default. Use it only when the reason says why typography, data, or editable shapes are stronger than any bitmap.
5. Use real or source-backed images for factual, screenshot, chart, logo, real-location, or person-accuracy content.
6. Do not create generic decorative filler; generated images need a clear narrative job.

## 2. Trigger rules

1. Use `generate` for cover, divider, poster, campaign, launch, vision, abstract concept, future-state, transformation, and emotionally led closing slides.
2. Use `generate` for investor pitch, fundraising, product-demo, premium B2B SaaS, executive keynote, or launch-event slides when the user gives visual direction such as high-end, premium, credible, dark, keynote-like, VC-facing, or "贵气/靠谱/发布会感". At minimum, choose `generate` for the cover and one solution/product/vision hero slide unless the user opts out or a real/source-backed asset is required.
3. Use `generate` for realistic/semi-realistic product mockups, environments, textures, human scenes, or hero/card visuals that would be awkward or low-quality if drawn from PowerPoint shapes.
4. Use `generate` when the user asks for image-rich, illustration, scene, poster, cinematic, magazine, campaign, or visual-metaphor output.
5. Use `draw_in_html` for dense data, maps, timelines, architecture, process, and tables when editability is more important than bitmap impact.
6. Use `skip` for data slides only when charts and text are stronger and no local visual frame would help.
7. Use `use_existing` for supplied product photos, charts, official logos, real locations, screenshots, named people, or source-captured visuals.

## 3. Manifest format

1. Keep a deck-level `assets/generated/manifest.json` with `deck_context`, `style_anchor`, and `image_plan`.
2. For every slide that uses a generated full-bleed or full-slide background, record a `layout_contract` before writing the prompt. The contract is the source of truth for text placement; image prompts are derived from it, not guessed independently.
3. Use the fixed slide coordinate system `1920x1080`. Record text regions as `{ x, y, width, height }` in pixels, matching the HTML/CSS boxes that will be used in `deck.html`.
4. If the text layout is not fixed yet, draft the layout first. Do not generate a full-slide image from a vague instruction such as "leave room for title".
5. Small or medium generated hero images placed in fixed frames do not need `layout_contract` by default. Give them an explicit `placement`/frame size and keep them out of text flow; add `layout_contract` only if the image visually overlaps or sits behind text.
6. Use this shape for each slide needing visuals:

```json
{
  "slide": "03",
  "decision": "generate",
  "kind": "hero_illustration",
  "reason": "text message needs visual anchor",
  "placement": "right hero",
  "layout_contract": {
    "slide_size": { "width": 1920, "height": 1080 },
    "text_regions": [
      { "name": "title", "x": 120, "y": 155, "width": 700, "height": 150 },
      { "name": "body", "x": 120, "y": 360, "width": 620, "height": 360 }
    ],
    "visual_focus_regions": [
      { "name": "hero", "x": 900, "y": 120, "width": 860, "height": 780 }
    ],
    "safe_background_rule": "Keep the left text column low-detail and low-contrast, but not blank: use faint thematic texture, atmospheric continuation, or pale abstract shapes. Avoid faces, strong objects, highlights, hard edges, or readable symbols."
  },
  "aspect_ratio": "16:9",
  "target_size": "2848x1600",
  "prompt": {
    "deck_context": "AI Operating Model Transformation deck for executive and product leadership; theme: moving from isolated AI pilots to governed, repeatable AI workflows",
    "subject": "Three abstract data streams converging into a central node",
    "composition": "right-side hero inside x=900,y=120,w=860,h=780; left text-safe area x=120,y=155,w=700,h=565 remains low-detail and low-contrast with faint thematic texture and atmospheric continuation, not empty blank space",
    "style": "Editorial vector illustration, clean linework, soft gradients",
    "palette": "Deep indigo #1E2A5E, electric cyan #22D3EE, amber #F59E0B, off-white #F8FAFC",
    "lighting": "Soft directional rim light",
    "mood": "Forward-looking and calm",
    "quality": "High detail, crisp edges, 4K finish"
  },
  "avoid": "embedded text, watermark, named people, blurry output",
  "output_path": "assets/generated/slide-03-hero.png",
  "alt_text": "Abstract AI workflow illustration"
}
```

1. Use structured prompt fields for `generate`.
2. Put `deck_context` first in every `generate` prompt so the image model sees the whole PPT theme before the slide-specific subject.
3. Keep `avoid` separate from `prompt`.
4. Put text-region coordinates into the `composition` field in human-readable form. Example: `title/body safe area x=120,y=155,w=700,h=565; keep this region calm and low contrast with faint thematic texture, not blank; place visual focus on right`.
5. The final HTML must implement the same `layout_contract.text_regions` values for text-bearing elements. If the HTML positions change, update the manifest and regenerate or revise the image prompt.
6. Each text-bearing HTML element covered by `layout_contract.text_regions` must carry `data-layout-region="<region name>"`. Run `scripts/validate_image_layout_contract.js deck.html assets/generated/manifest.json` before HTML self-check to compare actual DOM boxes with the manifest. The validator only requires contracts for generated full-slide/background images; ordinary fixed-frame hero images are not blocked by this gate.

## 4. Style anchor reuse

1. Reuse deck `style_anchor` for every generated prompt.
2. Keep generated prompt styles consistent with deck voice and palette.
3. Avoid arbitrary dimensions.
4. Use preset `2848x1600` for 16:9 hero/background.
5. Use preset `2048x2048` for square spot.

## 5. Output placement

1. Store generated files under `assets/generated/`.
1. Reference files with relative paths inside HTML.
1. Always call `generate_image` with `watermark: false` for PPT assets. The deck supplies its own branding/watermark and the `avoid` field already steers the model away from in-image watermarks, so the tool's default "AI 生成" stamp must be suppressed.
1. If generation tooling is unavailable, mark appropriate image-plan entries as `blocked` or choose `draw_in_html`; do not silently convert strong `generate` candidates to `skip` just to avoid the missing tool.
1. In `creative_image_mode`, the previous fallback rule is stricter: if the required generated image is unavailable, the overall deck is blocked even if some slides can be drawn in HTML.
