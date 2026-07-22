(function attachControlledDeckLayouts(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.__deckLayoutRegistry = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function createControlledDeckLayouts() {
"use strict";

const EDITOR_PLACEHOLDER_IMAGE =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";

function textField(maxChars, options = {}) {
  return {
    type: "text",
    maxChars,
    required: options.required !== false,
    editor: options.editor !== false,
    role: options.role || "body",
  };
}

function enumField(values, defaultValue) {
  return {
    type: "enum",
    values,
    default: defaultValue,
    required: false,
    editor: true,
  };
}

function mediaField(options = {}) {
  return {
    type: "media",
    required: options.required === true,
    editor: true,
    aspectRatio: options.aspectRatio || "16:9",
    allowedKinds: ["image"],
  };
}

function arrayField(minItems, maxItems, itemShape) {
  return {
    type: "array",
    required: true,
    editor: true,
    minItems,
    maxItems,
    itemShape,
  };
}

function objectField(shape, options = {}) {
  return {
    type: "object",
    required: options.required !== false,
    editor: true,
    shape,
  };
}

function mediaSlots(min, max, ratios, options = {}) {
  const backgroundMode = options.backgroundMode || "subtle";
  const backgroundRules = {
    expressive: {
      recommendation: "preferred",
      useWhen: ["cover", "divider", "vision", "poster", "cinematic-pause"],
      avoidWhen: ["dense-data", "table", "long-body"],
    },
    subtle: {
      recommendation: "optional",
      useWhen: ["atmosphere", "brand-texture", "low-detail-context"],
      avoidWhen: ["dense-data", "table", "high-contrast-detail-behind-copy"],
    },
    rare: {
      recommendation: "rare",
      useWhen: ["faint-brand-texture"],
      avoidWhen: ["data-legibility-risk", "busy-scene", "high-contrast-detail-behind-copy"],
    },
  };
  return {
    min,
    max,
    ratios,
    countIncludesBackground: false,
    decision: {
      mode: "auto",
      rule: options.decisionRule ||
        "Choose generate, use_existing, or skip from the narrative job; do not add decorative filler.",
    },
    slots: options.slots || [],
    background: {
      supported: true,
      path: "background",
      strategies: ["generate", "use_existing", "skip"],
      preferredRatio: "16:9",
      treatments: ["wash-light", "wash-dark", "none"],
      requiresLayoutContract: true,
      textRegionNames: options.textRegionNames || [],
      ...(backgroundRules[backgroundMode] || backgroundRules.subtle),
    },
  };
}

function deepClone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function textValue(value) {
  return typeof value === "string" ? value.trim() : "";
}

function firstText(...values) {
  return values.map(textValue).find(Boolean) || "";
}

function fitText(value, maxChars, fallback = "") {
  const text = firstText(value, fallback);
  return Array.from(text).slice(0, maxChars).join("");
}

function characterLength(value) {
  return Array.from(String(value == null ? "" : value).trim()).length;
}

function isCompactMetric(value) {
  const text = String(value == null ? "" : value).trim();
  if (!text || characterLength(text) > 12) return false;
  return (
    /^[0-9０-９][0-9０-９.,:：/+%％×xX￥$¥€£\s-]*(?:年|月|日|队|国|城|页|个|项|种|倍)?$/u.test(text) ||
    /^[A-Za-z0-9][A-Za-z0-9 .:+/%_-]*$/.test(text) ||
    /^(?:∞|零|无|是|否)$/u.test(text)
  );
}

function statementProofStyle(props) {
  const requested = props.proof_style || "auto";
  if (requested !== "auto") return requested;
  const values = (props.proofs || []).map(item => item.value);
  return values.length && values.every(isCompactMetric) ? "metrics" : "points";
}

function numericValue(value) {
  const match = String(value == null ? "" : value)
    .replace(/,/g, "")
    .match(/-?\d+(?:\.\d+)?/);
  const parsed = match ? Number(match[0]) : 0;
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function isAutomaticOrdinal(value, index) {
  const text = textValue(value);
  if (!/^\d+$/.test(text)) return false;
  return Number(text) === index + 1;
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function editableText(tag, path, value, className = "", attributes = {}) {
  const classAttr = className ? ` class="${escapeHtml(className)}"` : "";
  const extraAttrs = Object.entries(attributes)
    .map(([name, attributeValue]) => ` ${escapeHtml(name)}="${escapeHtml(attributeValue)}"`)
    .join("");
  return `<${tag}${classAttr} data-prop-path="${escapeHtml(path)}" data-prop-kind="text"${extraAttrs}>${escapeHtml(value)}</${tag}>`;
}

function editableTableCell(tag, path, value, className = "") {
  const classAttr = className ? ` class="${escapeHtml(className)}"` : "";
  return `<${tag}${classAttr}>${editableText("span", path, value, "data-table-cell-text")}</${tag}>`;
}

function image(path, media, className = "", modelRoot = "props") {
  const src = media && media.src ? media.src : "";
  const alt = media && media.alt ? media.alt : "";
  const classes = [
    className,
    src === EDITOR_PLACEHOLDER_IMAGE ? "editor-placeholder-image" : "",
  ].filter(Boolean).join(" ");
  const classAttr = classes ? ` class="${escapeHtml(classes)}"` : "";
  const fit = ["cover", "contain"].includes(media && media.fit) ? media.fit : "cover";
  const positions = {
    center: "center center",
    left: "left center",
    right: "right center",
    top: "center top",
    bottom: "center bottom",
  };
  const position = positions[media && media.position] || positions.center;
  const origin = ["generated", "asset", "uploaded"].includes(media && media.origin)
    ? ` data-media-origin="${escapeHtml(media.origin)}"`
    : "";
  const rootAttr = modelRoot === "slide" ? ' data-model-root="slide"' : "";
  if (!src) {
    return `<div${classAttr} data-media-placeholder="true"${rootAttr} data-prop-path="${escapeHtml(path)}" data-prop-kind="image"><span>IMAGE</span></div>`;
  }
  return `<img${classAttr} src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" style="object-fit:${fit};object-position:${position}"${origin}${rootAttr} data-prop-path="${escapeHtml(path)}" data-prop-kind="image" />`;
}

const COMPOSITION_HTML_TEMPLATES = Object.freeze({
  "institutional-grid": "ledger",
  "editorial-spread": "spread",
  "poster-asymmetric": "stage",
  "playful-collage": "collage",
  "brutalist-frame": "frame",
  "retro-interface": "window",
  "literary-minimal": "article",
  "product-showcase": "device",
  "cinematic-canvas": "cinema",
  "analytical-exhibit": "exhibit",
  "technical-schematic": "schematic",
});

let activeCompositionDesign = null;

function normalizedCompositionDesign(design) {
  const requestedFamily = design && typeof design.family === "string"
    ? design.family
    : "";
  const family = COMPOSITION_HTML_TEMPLATES[requestedFamily]
    ? requestedFamily
    : "institutional-grid";
  return {
    family,
    template: COMPOSITION_HTML_TEMPLATES[family],
    variant: design && typeof design.variant === "string" ? design.variant : "default",
  };
}

function compositionHtml(content, design) {
  const { family, template, variant } = normalizedCompositionDesign(design);
  const attrs = `data-composition-template="${template}" data-composition-family="${family}" data-composition-variant="${escapeHtml(variant)}"`;
  if (template === "spread") {
    return [
      `<article class="composition-root composition-spread" ${attrs}>`,
      '  <header class="composition-spread-folio composition-ornament" aria-hidden="true"><i></i><i></i></header>',
      '  <div class="composition-spread-body">',
      `    <div class="composition-content" data-composition-region="content">${content}</div>`,
      "  </div>",
      "</article>",
    ].join("\n");
  }
  if (template === "stage") {
    return [
      `<div class="composition-root composition-stage" ${attrs}>`,
      '  <span class="composition-stage-block composition-ornament" aria-hidden="true"></span>',
      `  <main class="composition-content" data-composition-region="content">${content}</main>`,
      '  <span class="composition-stage-index composition-ornament" aria-hidden="true"></span>',
      "</div>",
    ].join("\n");
  }
  if (template === "collage") {
    return [
      `<section class="composition-root composition-collage" ${attrs}>`,
      '  <i class="composition-collage-pin composition-collage-pin-a composition-ornament" aria-hidden="true"></i>',
      '  <div class="composition-collage-board">',
      `    <div class="composition-content" data-composition-region="content">${content}</div>`,
      "  </div>",
      '  <i class="composition-collage-pin composition-collage-pin-b composition-ornament" aria-hidden="true"></i>',
      "</section>",
    ].join("\n");
  }
  if (template === "frame") {
    return [
      `<div class="composition-root composition-frame" ${attrs}>`,
      '  <header class="composition-frame-edge composition-frame-edge-top composition-ornament" aria-hidden="true"></header>',
      `  <main class="composition-content" data-composition-region="content">${content}</main>`,
      '  <footer class="composition-frame-edge composition-frame-edge-bottom composition-ornament" aria-hidden="true"></footer>',
      "</div>",
    ].join("\n");
  }
  if (template === "window") {
    return [
      `<div class="composition-root composition-window" ${attrs}>`,
      '  <div class="composition-window-bar composition-ornament" aria-hidden="true"><i></i><i></i><i></i></div>',
      '  <div class="composition-window-pane">',
      `    <main class="composition-content" data-composition-region="content">${content}</main>`,
      "  </div>",
      "</div>",
    ].join("\n");
  }
  if (template === "article") {
    return [
      `<article class="composition-root composition-article" ${attrs}>`,
      '  <header class="composition-article-folio composition-ornament" aria-hidden="true"><span></span></header>',
      `  <section class="composition-content" data-composition-region="content">${content}</section>`,
      "</article>",
    ].join("\n");
  }
  if (template === "device") {
    const ornaments = variant === "browser-story"
      ? [
          '  <header class="composition-device-browserbar composition-ornament" aria-hidden="true"><i></i><span></span><b></b></header>',
        ]
      : variant === "annotated-flow"
        ? [
            '  <aside class="composition-device-callouts composition-ornament" aria-hidden="true"><span></span><span></span><span></span></aside>',
          ]
        : [
            '  <aside class="composition-device-bezel composition-ornament" aria-hidden="true"><i></i><span></span><i></i></aside>',
          ];
    return [
      `<section class="composition-root composition-device" ${attrs}>`,
      ...ornaments,
      '  <div class="composition-device-screen">',
      `    <main class="composition-content" data-composition-region="content">${content}</main>`,
      "  </div>",
      "</section>",
    ].join("\n");
  }
  if (template === "cinema") {
    return [
      `<section class="composition-root composition-cinema" ${attrs}>`,
      '  <div class="composition-cinema-matte composition-cinema-matte-top composition-ornament" aria-hidden="true"></div>',
      '  <div class="composition-cinema-timecode composition-ornament" aria-hidden="true"><i></i><span></span><i></i></div>',
      '  <div class="composition-cinema-frame">',
      `    <main class="composition-content" data-composition-region="content">${content}</main>`,
      "  </div>",
      '  <aside class="composition-cinema-cue composition-ornament" aria-hidden="true"><i></i><span></span></aside>',
      '  <div class="composition-cinema-matte composition-cinema-matte-bottom composition-ornament" aria-hidden="true"></div>',
      "</section>",
    ].join("\n");
  }
  if (template === "exhibit") {
    const ornaments = variant === "evidence-rail"
      ? [
          '  <aside class="composition-exhibit-scale composition-ornament" aria-hidden="true"><i></i><i></i><i></i><i></i><span></span></aside>',
          '  <aside class="composition-exhibit-legend composition-ornament" aria-hidden="true"><i></i><i></i><i></i></aside>',
        ]
      : variant === "decision-board"
        ? [
            '  <aside class="composition-exhibit-decisions composition-ornament" aria-hidden="true"><span></span><span></span><span></span></aside>',
          ]
        : [
            '  <header class="composition-exhibit-axis composition-ornament" aria-hidden="true"><i></i><span></span></header>',
            '  <aside class="composition-exhibit-key composition-ornament" aria-hidden="true"><i></i><i></i><i></i></aside>',
          ];
    return [
      `<article class="composition-root composition-exhibit" ${attrs}>`,
      ...ornaments,
      '  <div class="composition-exhibit-board">',
      `    <main class="composition-content" data-composition-region="content">${content}</main>`,
      "  </div>",
      "</article>",
    ].join("\n");
  }
  if (template === "schematic") {
    const ornaments = variant === "annotated-system"
      ? [
          '  <div class="composition-schematic-bus composition-ornament" aria-hidden="true"><i></i><i></i><i></i></div>',
          '  <aside class="composition-schematic-nodes composition-ornament" aria-hidden="true"><i></i><i></i><i></i><span></span></aside>',
        ]
      : variant === "spec-sheet"
        ? [
            '  <aside class="composition-schematic-spec-rail composition-ornament" aria-hidden="true"><i></i><i></i><i></i><i></i></aside>',
            '  <span class="composition-schematic-spec-mark composition-ornament" aria-hidden="true"></span>',
          ]
        : [
            '  <i class="composition-schematic-corner composition-schematic-corner-a composition-ornament" aria-hidden="true"></i>',
            '  <div class="composition-schematic-registration composition-ornament" aria-hidden="true"><i></i><span></span></div>',
            '  <i class="composition-schematic-corner composition-schematic-corner-b composition-ornament" aria-hidden="true"></i>',
          ];
    return [
      `<section class="composition-root composition-schematic" ${attrs}>`,
      ...ornaments,
      '  <div class="composition-schematic-canvas">',
      `    <main class="composition-content" data-composition-region="content">${content}</main>`,
      "  </div>",
      "</section>",
    ].join("\n");
  }
  return [
    `<div class="composition-root composition-ledger" ${attrs}>`,
    '  <aside class="composition-ledger-rail composition-ornament" aria-hidden="true"><span></span><span></span></aside>',
    '  <div class="composition-ledger-sheet">',
    `    <div class="composition-content" data-composition-region="content">${content}</div>`,
    "  </div>",
    "</div>",
  ].join("\n");
}

function slideFrame(slide, index, layoutClass, content) {
  const slideNumber = String(index + 1).padStart(2, "0");
  const composition = normalizedCompositionDesign(activeCompositionDesign);
  const background = slide.background && slide.background.src ? slide.background : null;
  const treatment = background && ["wash-light", "wash-dark", "none"].includes(background.treatment)
    ? background.treatment
    : "wash-light";
  const backgroundClass = background ? ` has-background background-${treatment}` : "";
  const backgroundOrigin = background && ["generated", "asset", "uploaded"].includes(background.origin)
    ? ` data-background-origin="${escapeHtml(background.origin)}"`
    : "";
  const backgroundHtml = background
    ? `<div class="slide-background" aria-hidden="true">${image("background.src", background, "slide-background-image", "slide")}</div>`
    : "";
  return [
    `<section class="slide ${layoutClass} has-composition-html${backgroundClass}" data-slide="${slideNumber}" data-slide-id="${escapeHtml(slide.id)}" data-layout-id="${escapeHtml(slide.layout_id)}" data-composition-template="${composition.template}"${backgroundOrigin}>`,
    backgroundHtml,
    `  <div class="deck-page" aria-hidden="true">${slideNumber}</div>`,
    compositionHtml(content, composition),
    "</section>",
  ].join("\n");
}

function renderCover(slide, index) {
  const p = slide.props;
  const hasHero = p.hero && p.hero.src;
  const mediaSide = p.media_side || "right";
  const classes = ["layout-cover", hasHero ? "has-hero" : "no-hero", `media-${mediaSide}`].join(" ");
  const copy = [
    '<div class="cover-copy" data-layout-region="cover-copy">',
    editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
    '<div class="accent-rule"></div>',
    editableText("h1", "title", p.title),
    editableText("p", "subtitle", p.subtitle, "lead"),
    editableText("p", "meta", p.meta || "", "meta"),
    "</div>",
  ].join("\n");
  const visual = hasHero
    ? `<div class="cover-visual">${image("hero.src", p.hero, "cover-image")}</div>`
    : '<div class="cover-visual cover-media-placeholder" data-media-slot="hero" data-prop-path="hero.src" data-prop-kind="image" aria-label="可选主视觉位置；编辑模式下双击可替换"><span aria-hidden="true"></span></div>';
  return slideFrame(slide, index, classes, `${copy}\n${visual}`);
}

function renderSection(slide, index) {
  const p = slide.props;
  return slideFrame(
    slide,
    index,
    `layout-section section-${p.alignment || "left"}`,
    [
      '<div class="section-index" data-layout-region="section-index">',
      editableText("span", "number", p.number, "section-number"),
      '<span class="section-line"></span>',
      "</div>",
      '<div class="section-copy" data-layout-region="section-copy">',
      editableText("p", "eyebrow", p.eyebrow || "SECTION", "eyebrow"),
      editableText("h1", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "lead"),
      "</div>",
      '<div class="section-mark" aria-hidden="true"></div>',
    ].join("\n")
  );
}

function renderStatement(slide, index) {
  const p = slide.props;
  const proofStyle = statementProofStyle(p);
  const proofs = (p.proofs || [])
    .map((item, itemIndex) => [
      '<div class="proof-item">',
      `<span class="proof-index" aria-hidden="true">${String(itemIndex + 1).padStart(2, "0")}</span>`,
      editableText("strong", `proofs.${itemIndex}.value`, item.value, "proof-value"),
      textValue(item.label)
        ? editableText("span", `proofs.${itemIndex}.label`, item.label, "proof-label")
        : "",
      "</div>",
    ].join(""))
    .join("\n");
  return slideFrame(
    slide,
    index,
    `layout-statement statement-${p.emphasis || "balanced"}`,
    [
      '<div class="statement-top">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      '<span class="statement-rule"></span>',
      "</div>",
      `<div class="statement-main ${proofs ? "has-proofs" : "no-proofs"} proofs-${proofStyle}">`,
      '<div class="statement-narrative" data-layout-region="statement-narrative">',
      editableText("h1", "statement", p.statement, "statement-copy"),
      editableText("p", "support", p.support || "", "statement-support"),
      "</div>",
      proofs ? `<div class="proof-stack" data-layout-region="statement-proofs" aria-label="关键证明">${proofs}</div>` : "",
      "</div>",
    ].join("\n")
  );
}

function renderCards(slide, index) {
  const p = slide.props;
  const cards = p.items.map((item, itemIndex) => {
    const kicker = isAutomaticOrdinal(item.kicker, itemIndex)
      ? ""
      : item.kicker || "";
    return [
      `<article class="content-card" data-item-index="${itemIndex}">`,
      `<span class="card-index">${String(itemIndex + 1).padStart(2, "0")}</span>`,
      '<div class="card-copy">',
      editableText("p", `items.${itemIndex}.kicker`, kicker, "card-kicker"),
      editableText("h3", `items.${itemIndex}.title`, item.title),
      editableText("p", `items.${itemIndex}.body`, item.body, "card-body"),
      "</div>",
      "</article>",
    ].join("\n");
  }).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-cards cards-${p.variant || "balanced"} cards-count-${p.items.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="cards-grid" data-layout-region="content">${cards}</div>`,
    ].join("\n")
  );
}

function comparisonColumn(side, value) {
  const items = value.items.map((item, index) => editableText("li", `${side}.items.${index}`, item)).join("\n");
  return [
    `<article class="comparison-column comparison-${side}">`,
    editableText("p", `${side}.label`, value.label, "comparison-label"),
    editableText("h3", `${side}.title`, value.title),
    `<ul>${items}</ul>`,
    editableText("p", `${side}.footer`, value.footer || "", "comparison-footer"),
    "</article>",
  ].join("\n");
}

function renderComparison(slide, index) {
  const p = slide.props;
  return slideFrame(
    slide,
    index,
    `layout-comparison comparison-${p.variant || "contrast"}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      "</header>",
      '<div class="comparison-grid" data-layout-region="content">',
      comparisonColumn("left", p.left),
      '<div class="comparison-arrow" aria-hidden="true">→</div>',
      comparisonColumn("right", p.right),
      "</div>",
    ].join("\n")
  );
}

function renderKpis(slide, index) {
  const p = slide.props;
  const items = p.items.map((item, itemIndex) => [
    `<article class="kpi-card" data-item-index="${itemIndex}">`,
    editableText("p", `items.${itemIndex}.label`, item.label, "kpi-label"),
    editableText("p", `items.${itemIndex}.value`, item.value, "kpi-value"),
    editableText("p", `items.${itemIndex}.detail`, item.detail, "kpi-detail"),
    editableText("p", `items.${itemIndex}.delta`, item.delta || "", "kpi-delta"),
    "</article>",
  ].join("\n")).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-kpis kpis-${p.variant || "cards"} kpis-count-${p.items.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="kpi-grid" data-layout-region="content">${items}</div>`,
    ].join("\n")
  );
}

function renderArchitecture(slide, index) {
  const p = slide.props;
  const layers = (p.layers || []).map((layer, layerIndex) => {
    const modules = (layer.modules || []).map((module, moduleIndex) => [
      `<span class="architecture-module" data-module-index="${moduleIndex}">`,
      editableText(
        "span",
        `layers.${layerIndex}.modules.${moduleIndex}`,
        module,
        "architecture-module-text"
      ),
      "</span>",
    ].join("\n")).join("\n");
    return [
      `<article class="architecture-layer" data-item-index="${layerIndex}">`,
      `<span class="architecture-index" aria-hidden="true">${String(layerIndex + 1).padStart(2, "0")}</span>`,
      '<div class="architecture-layer-heading">',
      editableText("p", `layers.${layerIndex}.label`, layer.label || "", "architecture-label"),
      editableText("h3", `layers.${layerIndex}.title`, layer.title),
      "</div>",
      `<div class="architecture-modules">${modules}</div>`,
      "</article>",
    ].join("\n");
  }).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-architecture architecture-${p.variant || "stack"} architecture-count-${(p.layers || []).length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="architecture-layers" data-layout-region="content">${layers}</div>`,
      editableText("p", "note", p.note || "", "architecture-note"),
    ].join("\n")
  );
}

function renderIntegrationNode(item, itemIndex, side) {
  return [
    `<article class="integration-node integration-node-${side}" data-item-index="${itemIndex}">`,
    editableText("h3", `systems.${itemIndex}.title`, item.title),
    editableText("p", `systems.${itemIndex}.flow`, item.flow, "integration-flow"),
    '<span class="integration-connector" aria-hidden="true"></span>',
    "</article>",
  ].join("\n");
}

function renderSystemIntegration(slide, index) {
  const p = slide.props;
  const systems = p.systems || [];
  const splitAt = Math.ceil(systems.length / 2);
  const left = systems
    .slice(0, splitAt)
    .map((item, itemIndex) => renderIntegrationNode(item, itemIndex, "left"))
    .join("\n");
  const right = systems
    .slice(splitAt)
    .map((item, offset) => renderIntegrationNode(item, splitAt + offset, "right"))
    .join("\n");
  return slideFrame(
    slide,
    index,
    `layout-system-integration integration-${p.variant || "hub-spoke"} integration-count-${systems.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      '<div class="integration-map" data-layout-region="content">',
      `<div class="integration-side integration-side-left">${left}</div>`,
      '<article class="integration-hub">',
      editableText("p", "hub.label", p.hub.label || "", "integration-hub-label"),
      editableText("h3", "hub.title", p.hub.title),
      editableText("p", "hub.body", p.hub.body, "integration-hub-body"),
      '<span class="integration-hub-arrow" aria-hidden="true">↔</span>',
      "</article>",
      `<div class="integration-side integration-side-right">${right}</div>`,
      "</div>",
      editableText("p", "note", p.note || "", "integration-note"),
    ].join("\n")
  );
}

function technicalDiagramSpec(props) {
  return {
    version: 1,
    kind: props.diagram_kind || "architecture",
    direction: props.direction || "RIGHT",
    title: props.title || "Technical diagram",
    nodes: deepClone(props.nodes || []),
    edges: deepClone(props.edges || []),
  };
}

function createTechnicalDiagramPreset(kind = "architecture") {
  if (kind === "integration") {
    return deepClone({
      eyebrow: "系统集成",
      subtitle: "中心平台通过标准接口连接渠道、业务系统与数据服务",
      diagram_kind: "integration",
      direction: "RIGHT",
      nodes: [
        { id: "channels", label: "渠道与应用", detail: "Web · App · IM", kind: "client" },
        { id: "identity", label: "统一认证", detail: "SSO · 权限 · 租户", kind: "gateway" },
        { id: "platform", label: "AI 服务平台", detail: "会话 · 知识 · 工具", kind: "hub" },
        { id: "orders", label: "订单 / 工单", detail: "状态 · 流转 · 售后", kind: "external" },
        { id: "crm", label: "CRM / 会员", detail: "画像 · 等级 · 权益", kind: "external" },
        { id: "analytics", label: "数据与分析", detail: "指标 · 审计 · 看板", kind: "data" },
      ],
      edges: [
        { id: "edge-channels-identity", source: "channels", target: "identity", label: "登录 / 请求" },
        { id: "edge-identity-platform", source: "identity", target: "platform", label: "鉴权上下文" },
        { id: "edge-platform-orders", source: "platform", target: "orders", label: "API / 事件" },
        { id: "edge-platform-crm", source: "platform", target: "crm", label: "客户数据" },
        { id: "edge-platform-analytics", source: "platform", target: "analytics", label: "日志 / 指标" },
      ],
      note: "连接关系来自 DiagramSpec；接口方向、协议和数据边界可在 HTML 中继续调整。",
    });
  }
  if (kind === "pipeline") {
    return deepClone({
      eyebrow: "数据管道",
      subtitle: "从数据接入、缓冲、处理到存储和服务的端到端链路",
      diagram_kind: "pipeline",
      direction: "RIGHT",
      nodes: [
        { id: "sources", label: "业务数据源", detail: "DB · SaaS · 日志", kind: "client" },
        { id: "ingestion", label: "数据接入", detail: "CDC · API · Batch", kind: "gateway" },
        { id: "queue", label: "消息缓冲", detail: "Kafka · Retry · DLQ", kind: "queue" },
        { id: "processing", label: "流批处理", detail: "清洗 · 关联 · 特征", kind: "service" },
        { id: "lakehouse", label: "Lakehouse", detail: "Raw · Curated · Serving", kind: "data" },
        { id: "consumers", label: "数据服务", detail: "BI · API · ML", kind: "hub" },
      ],
      edges: [
        { id: "edge-sources-ingestion", source: "sources", target: "ingestion", label: "采集" },
        { id: "edge-ingestion-queue", source: "ingestion", target: "queue", label: "事件" },
        { id: "edge-queue-processing", source: "queue", target: "processing", label: "消费" },
        { id: "edge-processing-lakehouse", source: "processing", target: "lakehouse", label: "入湖" },
        { id: "edge-lakehouse-consumers", source: "lakehouse", target: "consumers", label: "查询 / 特征" },
      ],
      note: "节点和边可增删；重新布局后自动计算层级、间距和正交连线。",
    });
  }
  return deepClone({
    eyebrow: "技术架构",
    subtitle: "按入口、平台能力、业务集成与治理边界组织系统",
    diagram_kind: "architecture",
    direction: "RIGHT",
    nodes: [
      { id: "channel", label: "用户渠道", detail: "Web · App · IM", kind: "client" },
      { id: "gateway", label: "API Gateway", detail: "鉴权 · 限流 · 路由", kind: "gateway" },
      { id: "orchestrator", label: "AI Orchestrator", detail: "会话 · 工具 · 策略", kind: "hub" },
      { id: "knowledge", label: "知识检索", detail: "RAG · 向量索引", kind: "service" },
      { id: "business", label: "业务服务", detail: "订单 · CRM · 工单", kind: "external" },
      { id: "governance", label: "治理与观测", detail: "审计 · 指标 · 告警", kind: "data" },
    ],
    edges: [
      { id: "edge-channel-gateway", source: "channel", target: "gateway", label: "HTTPS" },
      { id: "edge-gateway-ai", source: "gateway", target: "orchestrator", label: "请求" },
      { id: "edge-ai-knowledge", source: "orchestrator", target: "knowledge", label: "检索" },
      { id: "edge-ai-business", source: "orchestrator", target: "business", label: "工具调用" },
      { id: "edge-ai-governance", source: "orchestrator", target: "governance", label: "日志 / 指标" },
    ],
    note: "PPTX 中导出为单个 SVG 矢量对象；节点级编辑保留在 HTML / DiagramSpec。",
  });
}

function renderTechnicalDiagramRoot(props) {
  const spec = technicalDiagramSpec(props);
  const encodedSpec = escapeHtml(JSON.stringify(spec));
  const label = {
    architecture: "ARCHITECTURE",
    integration: "SYSTEM INTEGRATION",
    pipeline: "DATA PIPELINE",
  }[spec.kind] || "TECHNICAL DIAGRAM";
  return [
    `<div class="technical-diagram-canvas" data-pptx-diagram data-diagram-spec="${encodedSpec}" data-diagram-kind="${escapeHtml(spec.kind)}" data-diagram-render-state="pending">`,
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 620" role="img" aria-label="Technical diagram loading">',
    '<rect width="1600" height="620" rx="24" fill="var(--deck-bg)" stroke="var(--deck-border)" stroke-width="2"/>',
    `<text x="800" y="294" text-anchor="middle" fill="var(--deck-primary)" font-family="Arial, sans-serif" font-size="20" font-weight="700" letter-spacing="3">${label}</text>`,
    '<text x="800" y="338" text-anchor="middle" fill="var(--deck-muted)" font-family="Arial, sans-serif" font-size="16">DiagramSpec · automatic layout</text>',
    '</svg>',
    '</div>',
  ].join("");
}

function renderTechnicalDiagram(slide, index) {
  const p = slide.props;
  return slideFrame(
    slide,
    index,
    `layout-technical-diagram technical-diagram-${p.diagram_kind || "architecture"}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      '</header>',
      `<div class="technical-diagram-stage" data-layout-region="content">${renderTechnicalDiagramRoot(p)}</div>`,
      editableText("p", "note", p.note || "", "technical-diagram-note"),
    ].join("\n")
  );
}

function renderDashboardOverview(slide, index) {
  const p = slide.props;
  const items = (p.items || []).map((item, itemIndex) => [
    `<article class="dashboard-domain" data-item-index="${itemIndex}">`,
    '<div class="dashboard-domain-heading">',
    `<span class="dashboard-domain-index" aria-hidden="true">${String(itemIndex + 1).padStart(2, "0")}</span>`,
    editableText("p", `items.${itemIndex}.label`, item.label || "", "dashboard-domain-label"),
    "</div>",
    editableText("h3", `items.${itemIndex}.title`, item.title),
    editableText("p", `items.${itemIndex}.detail`, item.detail, "dashboard-domain-detail"),
    "</article>",
  ].join("\n")).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-dashboard-overview dashboard-${p.variant || "management"} dashboard-count-${(p.items || []).length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="dashboard-domain-grid" data-layout-region="content">${items}</div>`,
      editableText("p", "insight", p.insight || "", "dashboard-insight"),
    ].join("\n")
  );
}

function renderTimeline(slide, index) {
  const p = slide.props;
  const bodyless = p.steps.every((step) => !String(step.body || "").trim());
  const steps = p.steps.map((step, stepIndex) => [
    `<article class="timeline-step" data-item-index="${stepIndex}">`,
    `<span class="timeline-number">${String(stepIndex + 1).padStart(2, "0")}</span>`,
    editableText("p", `steps.${stepIndex}.phase`, step.phase || "", "timeline-phase"),
    editableText("h3", `steps.${stepIndex}.title`, step.title),
    editableText("p", `steps.${stepIndex}.body`, step.body, "timeline-body"),
    "</article>",
  ].join("\n")).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-timeline timeline-${p.variant || "horizontal"} timeline-count-${p.steps.length}${bodyless ? " timeline-bodyless" : ""}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="timeline-track" data-layout-region="content">${steps}</div>`,
    ].join("\n")
  );
}

function renderProjectCase(slide, index) {
  const p = slide.props;
  const metrics = (p.metrics || []).map((metric, metricIndex) => [
    `<article class="project-case-metric" data-item-index="${metricIndex}">`,
    editableText("strong", `metrics.${metricIndex}.value`, metric.value, "project-case-value"),
    editableText("span", `metrics.${metricIndex}.label`, metric.label, "project-case-label"),
    "</article>",
  ].join("\n")).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-project-case project-${p.composition || "split"} media-${p.media_side || "right"}`,
    [
      `<div class="project-case-media">${image("image.src", p.image, "project-case-image")}</div>`,
      '<div class="project-case-copy" data-layout-region="project-copy">',
      '<div class="project-case-heading">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "positioning", p.positioning, "project-case-positioning"),
      "</div>",
      `<div class="project-case-metrics" data-layout-region="project-metrics">${metrics}</div>`,
      editableText("p", "caption", p.caption || "", "project-case-caption"),
      "</div>",
    ].join("\n")
  );
}

function renderImageHero(slide, index) {
  const p = slide.props;
  return slideFrame(
    slide,
    index,
    `layout-image-hero media-${p.media_side || "right"}`,
    [
      '<div class="image-hero-copy" data-layout-region="image-copy">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "body", p.body, "lead"),
      editableText("p", "caption", p.caption || "", "image-caption"),
      "</div>",
      `<div class="image-hero-media">${image("image.src", p.image, "hero-image")}</div>`,
    ].join("\n")
  );
}

function renderEditorialCover(slide, index) {
  const p = slide.props;
  const titleLength = Array.from(String(p.title || "").trim()).length;
  const titleFit = titleLength > 30
    ? "editorial-title-long"
    : titleLength > 16
      ? "editorial-title-medium"
      : "editorial-title-short";
  const tags = (p.tags || [])
    .map((tag, tagIndex) => editableText(
      "span",
      `tags.${tagIndex}`,
      tag,
      "editorial-cover-tag"
    ))
    .join("");
  return slideFrame(
    slide,
    index,
    `layout-cover-editorial cover-editorial-${p.alignment || "left"}`,
    [
      '<div class="editorial-cover-top" data-layout-region="editorial-cover-meta">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("p", "marker", p.marker || "", "editorial-cover-marker"),
      "</div>",
      '<div class="editorial-cover-copy" data-layout-region="editorial-cover-copy">',
      editableText("h1", "title", p.title, titleFit),
      editableText("p", "subtitle", p.subtitle, "lead"),
      tags ? `<div class="editorial-cover-tags">${tags}</div>` : "",
      "</div>",
      '<div class="editorial-cover-footer" data-layout-region="editorial-cover-meta">',
      editableText("p", "meta", p.meta || "", "meta"),
      '<span class="editorial-cover-rule" aria-hidden="true"></span>',
      "</div>",
    ].join("\n")
  );
}

function renderTextColumns(slide, index) {
  const p = slide.props;
  const sections = p.sections.map((section, sectionIndex) => {
    const bullets = (section.bullets || [])
      .map((bullet, bulletIndex) => editableText(
        "li",
        `sections.${sectionIndex}.bullets.${bulletIndex}`,
        bullet
      ))
      .join("\n");
    return [
      `<article class="text-section" data-item-index="${sectionIndex}">`,
      editableText("p", `sections.${sectionIndex}.label`, section.label || "", "text-section-label"),
      editableText("h3", `sections.${sectionIndex}.title`, section.title),
      editableText("p", `sections.${sectionIndex}.body`, section.body, "text-section-body"),
      bullets ? `<ul class="text-section-bullets">${bullets}</ul>` : "",
      "</article>",
    ].join("\n");
  }).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-text-columns text-${p.variant || "columns"} text-count-${p.sections.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="text-sections" data-layout-region="content">${sections}</div>`,
    ].join("\n")
  );
}

function renderBarChart(slide, index) {
  const p = slide.props;
  const values = p.items.map(item => numericValue(item.value));
  const chartSpec = {
    version: 1,
    type: p.variant === "columns" ? "column" : "bar",
    categories: p.items.map(item => item.label),
    series: [{ name: p.series_label || "数值", values }],
    legend: "off",
    show_values: "on",
    animation: "on",
    stacked: "off",
    value_suffix: "",
  };
  const fallback = p.items.map((item, itemIndex) => [
    `<span class="chart-fallback-item" data-item-index="${itemIndex}">`,
    `<span>${escapeHtml(item.label)}</span>`,
    `<strong>${escapeHtml(item.value)}</strong>`,
    "</span>",
  ].join("\n")).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-chart-bar chart-${p.variant || "horizontal"} chart-count-${p.items.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      `<div class="chart-body" data-layout-region="content">`,
      `<div class="chart-plot chart-echarts-frame" data-pptx-chart data-native-chart="true" data-chart-spec="${escapeHtml(JSON.stringify(chartSpec))}">`,
      '  <div class="echarts-for-pptx" data-chart-canvas role="img" aria-label="可编辑分类数据图表"></div>',
      `  <div class="chart-fallback" aria-hidden="true">${fallback}</div>`,
      "</div>",
      '<div class="chart-footer">',
      editableText("p", "insight", p.insight || "", "chart-insight"),
      editableText("p", "source", p.source || "", "chart-source"),
      "</div>",
      "</div>",
    ].join("\n")
  );
}

function normalizedChartSeries(series, categoryCount) {
  return (Array.isArray(series) ? series : []).slice(0, 4).map((item, seriesIndex) => ({
    name: firstText(item && item.name, `系列 ${seriesIndex + 1}`),
    values: Array.from({ length: categoryCount }, (_, valueIndex) =>
      String(item && Array.isArray(item.values) && item.values[valueIndex] != null
        ? item.values[valueIndex]
        : "0")
    ),
  }));
}

function chartValueUnit(value) {
  return String(value == null ? "" : value)
    .trim()
    .replace(/^-?\d+(?:,\d{3})*(?:\.\d+)?\s*/, "")
    .trim();
}

function chartCategoryUnits(series, categoryCount) {
  return Array.from({ length: categoryCount }, (_, categoryIndex) => {
    const units = new Set(
      series
        .map(item => chartValueUnit(item.values[categoryIndex]))
        .filter(Boolean)
    );
    return units.size === 1 ? [...units][0] : "";
  });
}

function renderChartFrame(chartSpec, fallback, extraClass = "") {
  const className = ["chart-echarts-frame", extraClass].filter(Boolean).join(" ");
  return [
    `<div class="${className}" data-pptx-chart data-native-chart="true" data-chart-spec="${escapeHtml(JSON.stringify(chartSpec))}">`,
    '  <div class="echarts-for-pptx" data-chart-canvas role="img" aria-label="可编辑多系列数据图表"></div>',
    `  <div class="chart-fallback" aria-hidden="true">${fallback}</div>`,
    "</div>",
  ].join("\n");
}

function renderDataChart(slide, index) {
  const p = slide.props;
  const categories = p.categories.slice(0, 12);
  const series = normalizedChartSeries(p.series, categories.length);
  const categoryUnits = chartCategoryUnits(series, categories.length);
  const distinctUnits = new Set(categoryUnits);
  const independentScales = !p.value_suffix
    && ["bar", "column"].includes(p.chart_type || "column")
    && p.stacked !== "on"
    && categories.length >= 2
    && categories.length <= 4
    && distinctUnits.size > 1
    && categoryUnits.some(Boolean);
  const inferredCommonSuffix = distinctUnits.size === 1 ? categoryUnits[0] : "";
  const chartSpec = {
    version: 1,
    type: p.chart_type || "column",
    categories,
    series: series.map(item => ({
      name: item.name,
      values: item.values.map(numericValue),
    })),
    legend: p.legend || "auto",
    show_values: p.show_values || "auto",
    animation: p.animation || "on",
    stacked: p.stacked || "off",
    value_suffix: p.value_suffix || inferredCommonSuffix || "",
  };
  const fallbackRows = categories.map((category, categoryIndex) => [
    '<span class="chart-fallback-item">',
    `<span>${escapeHtml(category)}</span>`,
    ...series.map(item => `<strong>${escapeHtml(item.values[categoryIndex])}</strong>`),
    "</span>",
  ].join("\n")).join("\n");
  let chartMarkup;
  if (independentScales) {
    const legend = series.length > 1
      ? [
        '<div class="chart-small-multiple-legend" aria-label="图表系列">',
        ...series.map(item => (
          `<span class="chart-small-multiple-legend-item">${escapeHtml(item.name)}</span>`
        )),
        "</div>",
      ].join("\n")
      : "";
    const panels = categories.map((category, categoryIndex) => {
      const panelSpec = {
        ...chartSpec,
        categories: [category],
        series: series.map(item => ({
          name: item.name,
          values: [numericValue(item.values[categoryIndex])],
        })),
        legend: "off",
        value_suffix: categoryUnits[categoryIndex] || "",
      };
      const fallback = [
        '<span class="chart-fallback-item">',
        `<span>${escapeHtml(category)}</span>`,
        ...series.map(item => `<strong>${escapeHtml(item.values[categoryIndex])}</strong>`),
        "</span>",
      ].join("\n");
      return renderChartFrame(panelSpec, fallback, "chart-small-multiple");
    }).join("\n");
    chartMarkup = [
      `<div class="chart-plot chart-small-multiples-wrap" data-chart-scale="independent">`,
      legend,
      `<div class="chart-small-multiples chart-small-multiples-count-${categories.length}">`,
      panels,
      "</div>",
      "</div>",
    ].join("\n");
  } else {
    chartMarkup = [
      '<div class="chart-plot chart-echarts-frame" data-pptx-chart data-native-chart="true" ',
      `data-chart-spec="${escapeHtml(JSON.stringify(chartSpec))}">`,
      '  <div class="echarts-for-pptx" data-chart-canvas role="img" aria-label="可编辑多系列数据图表"></div>',
      `  <div class="chart-fallback" aria-hidden="true">${fallbackRows}</div>`,
      "</div>",
    ].join("\n");
  }
  return slideFrame(
    slide,
    index,
    `layout-chart-data chart-type-${p.chart_type || "column"} chart-series-${series.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      '<div class="chart-body chart-data-body" data-layout-region="content">',
      chartMarkup,
      '<div class="chart-footer">',
      editableText("p", "insight", p.insight || "", "chart-insight"),
      editableText("p", "source", p.source || "", "chart-source"),
      "</div>",
      "</div>",
    ].join("\n")
  );
}

function renderDataTable(slide, index) {
  const p = slide.props;
  const isGantt = p.variant === "gantt" || /(?:甘特|gantt)/i.test(p.title || "");
  const columns = p.columns.slice(0, 6);
  const header = columns
    .map((column, columnIndex) => editableTableCell("th", `columns.${columnIndex}`, column))
    .join("\n");
  const rows = p.rows.map((row, rowIndex) => {
    const cells = columns.map((_, columnIndex) => {
      const value = row[columnIndex] || "—";
      const ganttState = isGantt && columnIndex > 0
        ? /^(?:■|●|◆|▰|█|进行|执行|active)$/i.test(String(value).trim())
          ? "gantt-cell gantt-active"
          : "gantt-cell gantt-idle"
        : "";
      return editableTableCell(
        "td",
        `rows.${rowIndex}.${columnIndex}`,
        value,
        ganttState
      );
    }).join("\n");
    return `<tr data-item-index="${rowIndex}">${cells}</tr>`;
  }).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-data-table table-${isGantt ? "gantt" : (p.variant || "ledger")} table-columns-${columns.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      '<div class="data-table-wrap" data-layout-region="content">',
      `<table class="data-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table>`,
      '<div class="table-footer">',
      editableText("p", "insight", p.insight || "", "table-insight"),
      editableText("p", "source", p.source || "", "table-source"),
      "</div>",
      "</div>",
    ].join("\n")
  );
}

function heatmapLevel(value, numericRange) {
  const label = String(value == null ? "" : value).trim().toLowerCase();
  if (/(?:极高|严重|关键|critical|urgent|very\s+high)/i.test(label)) return 5;
  if (/(?:较高|高|high)/i.test(label)) return 4;
  if (/(?:中等|中|medium|moderate)/i.test(label)) return 3;
  if (/(?:较低|低|low)/i.test(label)) return 2;
  if (/(?:无|未发生|none|n\/a|—|-)/i.test(label)) return 1;
  const numeric = Number(label.replace(/[%％,，]/g, ""));
  if (!Number.isFinite(numeric) || !numericRange) return 1;
  if (numericRange.max === numericRange.min) return 3;
  return Math.max(1, Math.min(5, Math.ceil(
    ((numeric - numericRange.min) / (numericRange.max - numericRange.min)) * 4 + 0.01
  )));
}

function renderHeatmapMatrix(slide, index) {
  const p = slide.props;
  const columns = p.columns.slice(0, 6);
  const rows = p.rows.slice(0, 8);
  const numericValues = rows
    .flatMap(row => row.slice(1, columns.length))
    .map(value => Number(String(value == null ? "" : value).replace(/[%％,，]/g, "")))
    .filter(Number.isFinite);
  const numericRange = numericValues.length
    ? { min: Math.min(...numericValues), max: Math.max(...numericValues) }
    : null;
  const header = columns.map((column, columnIndex) =>
    editableText(
      "div",
      `columns.${columnIndex}`,
      column,
      columnIndex === 0 ? "heatmap-corner-label" : "heatmap-column-label"
    )
  ).join("\n");
  const body = rows.map((row, rowIndex) => {
    const cells = columns.map((_, columnIndex) => {
      const value = row[columnIndex] || "待补充";
      if (columnIndex === 0) {
        return [
          '<div class="heatmap-row-label">',
          editableText(
            "span",
            `rows.${rowIndex}.${columnIndex}`,
            value,
            "heatmap-row-label-text"
          ),
          "</div>",
        ].join("");
      }
      const level = heatmapLevel(value, numericRange);
      return [
        `<div class="heatmap-cell heat-level-${level}" data-heat-level="${level}">`,
        editableText("span", `rows.${rowIndex}.${columnIndex}`, value, "heatmap-cell-value"),
        "</div>",
      ].join("");
    }).join("\n");
    return `<div class="heatmap-row" data-item-index="${rowIndex}">${cells}</div>`;
  }).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-heatmap-matrix heatmap-columns-${columns.length}`,
    [
      '<header class="slide-header" data-layout-region="header">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h2", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "header-note"),
      "</header>",
      '<div class="heatmap-body" data-layout-region="content">',
      `<div class="heatmap-grid"><div class="heatmap-header">${header}</div>${body}</div>`,
      '<div class="heatmap-legend" aria-label="热力强度">',
      editableText("span", "low_label", p.low_label || "低", "heatmap-legend-label"),
      '<span class="heatmap-legend-scale" aria-hidden="true"><i class="heat-level-1"></i><i class="heat-level-2"></i><i class="heat-level-3"></i><i class="heat-level-4"></i><i class="heat-level-5"></i></span>',
      editableText("span", "high_label", p.high_label || "高", "heatmap-legend-label"),
      "</div>",
      '<div class="heatmap-footer">',
      editableText("p", "insight", p.insight || "", "heatmap-insight"),
      editableText("p", "source", p.source || "", "heatmap-source"),
      "</div>",
      "</div>",
    ].join("\n")
  );
}

function renderClosing(slide, index) {
  const p = slide.props;
  const actions = (p.actions || []).map((action, actionIndex) => [
    `<article class="closing-action" data-item-index="${actionIndex}">`,
    `<span class="closing-action-index" aria-hidden="true">${String(actionIndex + 1).padStart(2, "0")}</span>`,
    '<div class="closing-action-copy">',
    editableText("h3", `actions.${actionIndex}.label`, action.label),
    editableText("p", `actions.${actionIndex}.detail`, action.detail, "closing-action-detail"),
    "</div>",
    "</article>",
  ].join("\n")).join("\n");
  return slideFrame(
    slide,
    index,
    `layout-closing closing-${p.variant || "next-steps"} closing-actions-${(p.actions || []).length}`,
    [
      '<div class="closing-copy" data-layout-region="closing-copy">',
      editableText("p", "eyebrow", p.eyebrow, "eyebrow"),
      editableText("h1", "title", p.title),
      editableText("p", "subtitle", p.subtitle || "", "lead"),
      editableText("p", "contact", p.contact || "", "closing-contact-line"),
      "</div>",
      actions ? `<div class="closing-actions" data-layout-region="closing-actions">${actions}</div>` : "",
      '<span class="closing-end-mark" aria-hidden="true">END</span>',
    ].join("\n")
  );
}

const layouts = [
  {
    id: "cover-hero-v1",
    label: "Hero cover",
    editor: {
      label: "封面",
      description: "标题、摘要与可选主视觉",
      controls: {
        enums: {
          media_side: {
            label: "图片位置",
            options: { left: "左侧", right: "右侧" },
          },
        },
      },
      defaultProps: {
        eyebrow: "年度作品集",
        title: "输入演示标题",
        subtitle: "用一句话说明这套演示要解决的问题",
        meta: "",
        hero: null,
        media_side: "right",
      },
    },
    roles: ["cover"],
    density: "low",
    contentShape: ["headline", "hero-media"],
    mediaSlots: mediaSlots(0, 1, ["16:9", "4:3"], {
      backgroundMode: "expressive",
      textRegionNames: ["cover-copy"],
      decisionRule: "Use hero for a concrete subject, background for atmosphere, or skip for a typography-led cover; prefer one dominant treatment.",
      slots: [{
        id: "hero",
        propPath: "hero",
        role: "primary-visual",
        required: false,
        strategies: ["generate", "use_existing", "skip"],
        preferredRatio: "4:3",
        placementControlledBy: "media_side",
      }],
    }),
    capabilities: ["editable", "pptx-safe", "generated-image"],
    variants: ["media-left", "media-right", "no-media"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(72, { role: "display" }),
      subtitle: textField(160, { role: "lead" }),
      meta: textField(64, { required: false, role: "caption" }),
      hero: mediaField({ required: false, aspectRatio: "4:3" }),
      media_side: enumField(["left", "right"], "right"),
    },
    defaultProps: { meta: "", hero: null, media_side: "right" },
    render: renderCover,
  },
  {
    id: "cover-editorial-v1",
    label: "Typography-led editorial cover",
    editor: {
      label: "文字封面",
      description: "大标题、期次标记与可选背景",
      controls: {
        enums: {
          alignment: {
            label: "标题对齐",
            options: { left: "左对齐", center: "居中" },
          },
        },
        collections: {
          tags: {
            label: "封面标签",
            itemDefault: "新标签",
          },
        },
      },
      defaultProps: {
        eyebrow: "主题演示",
        title: "输入一个值得被记住的标题",
        subtitle: "用一句简洁说明交代演示目的与核心范围。",
        marker: "2026",
        meta: "团队 · 日期",
        tags: [],
        alignment: "left",
      },
    },
    roles: ["cover", "title", "opening"],
    density: "low",
    contentShape: ["headline", "typography", "metadata", "tags"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "expressive",
      textRegionNames: ["editorial-cover-copy", "editorial-cover-meta"],
      decisionRule: "Prefer a typography-led cover; use a generated or existing background only when it adds atmosphere without competing with the title.",
    }),
    capabilities: ["editable", "pptx-safe", "generated-background"],
    variants: ["left", "center"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(84, { role: "display" }),
      subtitle: textField(160, { required: false, role: "lead" }),
      marker: textField(24, { required: false, role: "metric" }),
      meta: textField(72, { required: false, role: "caption" }),
      tags: arrayField(0, 6, textField(24, { role: "label" })),
      alignment: enumField(["left", "center"], "left"),
    },
    defaultProps: { subtitle: "", marker: "", meta: "", tags: [], alignment: "left" },
    render: renderEditorialCover,
  },
  {
    id: "section-marker-v1",
    label: "Section marker",
    editor: {
      label: "章节页",
      description: "章节序号与单一主题",
      controls: {
        enums: {
          alignment: {
            label: "内容对齐",
            options: { left: "左对齐", center: "居中" },
          },
        },
      },
      defaultProps: {
        number: "01",
        eyebrow: "SECTION",
        title: "输入章节标题",
        subtitle: "",
        alignment: "left",
      },
    },
    roles: ["section", "divider"],
    density: "low",
    contentShape: ["ordinal", "headline"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "expressive",
      textRegionNames: ["section-index", "section-copy"],
      decisionRule: "A calm generated or existing background may carry chapter atmosphere; otherwise keep the theme geometry.",
    }),
    capabilities: ["editable", "pptx-safe"],
    variants: ["left", "center"],
    fields: {
      number: textField(8, { role: "metric" }),
      eyebrow: textField(28, { required: false, role: "label" }),
      title: textField(56, { role: "display" }),
      subtitle: textField(140, { required: false, role: "lead" }),
      alignment: enumField(["left", "center"], "left"),
    },
    defaultProps: { eyebrow: "SECTION", subtitle: "", alignment: "left" },
    render: renderSection,
  },
  {
    id: "statement-focus-v1",
    label: "Single statement with metrics or proof points",
    editor: {
      label: "核心观点",
      description: "一句结论与最多三个证明点",
      controls: {
        enums: {
          proof_style: {
            label: "证明点样式",
            options: { auto: "自动", metrics: "数据", points: "要点" },
          },
          emphasis: {
            label: "观点强调",
            options: { balanced: "平衡", poster: "海报" },
          },
        },
        collections: {
          proofs: {
            label: "证明点",
            itemDefault: { value: "新证明点", label: "补充说明" },
          },
        },
      },
      defaultProps: {
        eyebrow: "核心观点",
        statement: "在这里写下最需要被记住的结论",
        support: "补充一句背景或解释，让结论更有支撑。",
        proofs: [],
        proof_style: "auto",
        emphasis: "balanced",
      },
    },
    roles: ["statement", "quote", "closing"],
    density: "medium-low",
    contentShape: ["statement", "proof-points"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "expressive",
      textRegionNames: ["statement-narrative", "statement-proofs"],
      decisionRule: "Use a background only when it strengthens the single statement and preserves a calm text-safe region.",
    }),
    capabilities: ["editable", "pptx-safe"],
    variants: ["balanced", "poster"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      statement: textField(120, { role: "display" }),
      support: textField(180, { required: false, role: "lead" }),
      proofs: arrayField(0, 3, {
        value: textField(36, { role: "metric-or-point" }),
        label: textField(52, { required: false, role: "caption" }),
      }),
      proof_style: enumField(["auto", "metrics", "points"], "auto"),
      emphasis: enumField(["balanced", "poster"], "balanced"),
    },
    defaultProps: { support: "", proofs: [], proof_style: "auto", emphasis: "balanced" },
    render: renderStatement,
  },
  {
    id: "cards-grid-v1",
    label: "Three to six structured cards",
    editor: {
      label: "要点卡片",
      description: "三到六个并列要点",
      controls: {
        enums: {
          variant: {
            label: "卡片样式",
            options: { balanced: "卡片", numbered: "编号" },
          },
        },
        collections: {
          items: {
            label: "卡片",
            itemDefault: { kicker: "NEW", title: "新要点", body: "补充这个要点的说明。" },
          },
        },
      },
      defaultProps: {
        eyebrow: "概览",
        title: "输入页面标题",
        subtitle: "",
        items: [
          { kicker: "01", title: "第一个要点", body: "用简短文字解释这个要点。" },
          { kicker: "02", title: "第二个要点", body: "用简短文字解释这个要点。" },
          { kicker: "03", title: "第三个要点", body: "用简短文字解释这个要点。" },
        ],
        variant: "balanced",
      },
    },
    roles: ["overview", "capabilities", "agenda", "use-cases"],
    density: "medium-high",
    contentShape: ["cards", "list"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
    }),
    capabilities: ["editable", "pptx-safe"],
    variants: ["balanced", "numbered"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      items: arrayField(3, 6, {
        kicker: textField(24, { required: false, role: "label" }),
        title: textField(36, { role: "heading" }),
        body: textField(100, { role: "body" }),
      }),
      variant: enumField(["balanced", "numbered"], "balanced"),
    },
    defaultProps: { subtitle: "", variant: "balanced" },
    render: renderCards,
  },
  {
    id: "text-columns-v1",
    label: "Two or three editorial text sections",
    editor: {
      label: "多栏文本",
      description: "两到三组长文本、说明与补充要点",
      controls: {
        enums: {
          variant: {
            label: "文本构图",
            options: { columns: "等宽分栏", lead: "主次分栏" },
          },
        },
        collections: {
          sections: {
            label: "文本区块",
            itemDefault: {
              label: "补充主题",
              title: "新的文本区块",
              body: "在这里补充一段完整说明。",
              bullets: [],
            },
          },
        },
      },
      defaultProps: {
        eyebrow: "详细说明",
        title: "输入需要展开说明的主题",
        subtitle: "把较长内容组织成清晰的阅读层级",
        sections: [
          {
            label: "01",
            title: "第一个主题",
            body: "用一段完整文字解释背景、判断或方法，避免把连续叙事拆成过多卡片。",
            bullets: ["可选的补充要点"],
          },
          {
            label: "02",
            title: "第二个主题",
            body: "用另一段文字展开不同侧面，并保持标题、正文和证据之间的清晰层级。",
            bullets: ["可选的补充要点"],
          },
        ],
        variant: "columns",
      },
    },
    roles: ["text", "analysis", "deep-dive", "narrative", "detail"],
    density: "high",
    contentShape: ["long-form", "columns", "sections"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "Keep long-form pages typography-led; use only a very faint background texture when readability is unaffected.",
    }),
    capabilities: ["editable", "pptx-safe", "long-copy"],
    variants: ["columns", "lead"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      sections: arrayField(2, 3, {
        label: textField(24, { required: false, role: "label" }),
        title: textField(40, { role: "heading" }),
        body: textField(180, { role: "body" }),
        bullets: arrayField(0, 3, textField(64, { role: "body" })),
      }),
      variant: enumField(["columns", "lead"], "columns"),
    },
    defaultProps: { subtitle: "", variant: "columns" },
    render: renderTextColumns,
  },
  {
    id: "comparison-two-column-v1",
    label: "Two-column comparison",
    editor: {
      label: "双栏对比",
      description: "两组观点、方案或前后状态",
      controls: {
        enums: {
          variant: {
            label: "对比样式",
            options: { contrast: "对比强调", symmetric: "左右对称" },
          },
        },
        collections: {
          "left.items": { label: "左侧要点", itemDefault: "新对比点" },
          "right.items": { label: "右侧要点", itemDefault: "新对比点" },
        },
      },
      defaultProps: {
        eyebrow: "对比",
        title: "输入对比主题",
        left: {
          label: "方案 A",
          title: "第一种选择",
          items: ["输入第一个对比点", "输入第二个对比点"],
          footer: "",
        },
        right: {
          label: "方案 B",
          title: "第二种选择",
          items: ["输入第一个对比点", "输入第二个对比点"],
          footer: "",
        },
        variant: "contrast",
      },
    },
    roles: ["comparison", "before-after", "decision"],
    density: "medium-high",
    contentShape: ["comparison", "two-column"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
    }),
    capabilities: ["editable", "pptx-safe"],
    variants: ["contrast", "symmetric"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      left: objectField({
        label: textField(24, { role: "label" }),
        title: textField(42, { role: "heading" }),
        items: arrayField(2, 5, textField(72, { role: "body" })),
        footer: textField(72, { required: false, role: "caption" }),
      }),
      right: objectField({
        label: textField(24, { role: "label" }),
        title: textField(42, { role: "heading" }),
        items: arrayField(2, 5, textField(72, { role: "body" })),
        footer: textField(72, { required: false, role: "caption" }),
      }),
      variant: enumField(["contrast", "symmetric"], "contrast"),
    },
    defaultProps: { variant: "contrast" },
    render: renderComparison,
  },
  {
    id: "kpi-grid-v1",
    label: "Three to six KPI cards",
    editor: {
      label: "关键数据",
      description: "三到六个指标与解释",
      controls: {
        enums: {
          variant: {
            label: "数据样式",
            options: { cards: "卡片", ledger: "账本" },
          },
        },
        collections: {
          items: {
            label: "指标",
            itemDefault: { label: "新指标", value: "00", detail: "补充数据说明。", delta: "" },
          },
        },
      },
      defaultProps: {
        eyebrow: "关键数据",
        title: "输入数据结论",
        subtitle: "",
        items: [
          { label: "指标一", value: "01", detail: "解释这个数字代表什么。", delta: "" },
          { label: "指标二", value: "02", detail: "解释这个数字代表什么。", delta: "" },
          { label: "指标三", value: "03", detail: "解释这个数字代表什么。", delta: "" },
        ],
        variant: "cards",
      },
    },
    roles: ["kpi", "dashboard", "traction", "results"],
    density: "medium-high",
    contentShape: ["metrics", "dashboard"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
    }),
    capabilities: ["editable", "pptx-safe", "data"],
    variants: ["cards", "ledger"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      items: arrayField(3, 6, {
        label: textField(36, { role: "caption" }),
        value: textField(18, { role: "metric" }),
        detail: textField(90, { required: false, role: "body" }),
        delta: textField(28, { required: false, role: "label" }),
      }),
      variant: enumField(["cards", "ledger"], "cards"),
    },
    defaultProps: { subtitle: "", variant: "cards" },
    render: renderKpis,
  },
  {
    id: "architecture-layered-v1",
    label: "Layered technical architecture",
    editor: {
      label: "分层架构",
      description: "三到六层技术架构与模块关系",
      controls: {
        enums: {
          variant: {
            label: "架构样式",
            options: { stack: "分层堆叠", ledger: "架构账本" },
          },
        },
        collections: {
          layers: {
            label: "架构层",
            itemDefault: {
              label: "LAYER",
              title: "新架构层",
              modules: ["模块一", "模块二"],
            },
          },
        },
      },
      defaultProps: {
        eyebrow: "解决方案架构",
        title: "输入技术分层架构结论",
        subtitle: "按职责边界组织触点、能力、集成与治理模块",
        layers: [
          { label: "TOUCHPOINT", title: "用户触点层", modules: ["官网 / APP", "小程序", "企业微信"] },
          { label: "AI SERVICE", title: "智能服务层", modules: ["意图识别", "知识检索", "会话路由"] },
          { label: "INTEGRATION", title: "业务集成层", modules: ["订单系统", "会员系统", "CRM / 工单"] },
          { label: "GOVERNANCE", title: "运营治理层", modules: ["数据看板", "安全审计", "运维监控"] },
        ],
        note: "层间通过标准接口连接，模块边界与责任归属保持清晰。",
        variant: "stack",
      },
    },
    roles: ["architecture", "system-design", "solution", "technology"],
    density: "high",
    contentShape: ["architecture", "layers", "modules"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The editable architecture diagram is the primary visual; keep the background quiet and structural.",
    }),
    capabilities: ["editable", "pptx-safe", "diagram"],
    variants: ["stack", "ledger"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      layers: arrayField(3, 6, {
        label: textField(24, { required: false, role: "label" }),
        title: textField(36, { role: "heading" }),
        modules: arrayField(2, 5, textField(28, { role: "body" })),
      }),
      note: textField(140, { required: false, role: "caption" }),
      variant: enumField(["stack", "ledger"], "stack"),
    },
    defaultProps: { subtitle: "", note: "", variant: "stack" },
    render: renderArchitecture,
  },
  {
    id: "system-integration-v1",
    label: "Hub-and-spoke system integration map",
    editor: {
      label: "系统集成",
      description: "中心平台与四到八个外围系统的数据流",
      controls: {
        enums: {
          variant: {
            label: "集成样式",
            options: { "hub-spoke": "中心辐射", bidirectional: "双向交换" },
          },
        },
        collections: {
          systems: {
            label: "外围系统",
            itemDefault: { title: "新系统", flow: "输入交换的数据或动作" },
          },
        },
      },
      defaultProps: {
        eyebrow: "系统集成",
        title: "输入系统连接与数据流结论",
        subtitle: "中心平台通过标准接口连接现有业务系统",
        hub: {
          label: "CORE PLATFORM",
          title: "AI 客服平台",
          body: "统一承接会话、知识、路由与人工协同",
        },
        systems: [
          { title: "订单系统", flow: "订单状态 · 物流 · 售后" },
          { title: "会员系统", flow: "身份 · 等级 · 权益" },
          { title: "CRM", flow: "客户画像 · 跟进记录" },
          { title: "工单系统", flow: "问题流转 · 处理状态" },
          { title: "统一认证", flow: "账号 · 权限 · 单点登录" },
          { title: "数据看板", flow: "指标汇总 · 运营分析" },
        ],
        note: "箭头表示信息双向流转；具体接口以客户现网能力为准。",
        variant: "hub-spoke",
      },
    },
    roles: ["integration", "data-flow", "system-map", "technology"],
    density: "high",
    contentShape: ["hub-spoke", "systems", "data-flow"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The editable integration map carries the page; avoid generated media and decorative network lines.",
    }),
    capabilities: ["editable", "pptx-safe", "diagram"],
    variants: ["hub-spoke", "bidirectional"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      hub: objectField({
        label: textField(24, { required: false, role: "label" }),
        title: textField(36, { role: "heading" }),
        body: textField(100, { role: "body" }),
      }),
      systems: arrayField(4, 8, {
        title: textField(32, { role: "heading" }),
        flow: textField(64, { role: "body" }),
      }),
      note: textField(140, { required: false, role: "caption" }),
      variant: enumField(["hub-spoke", "bidirectional"], "hub-spoke"),
    },
    defaultProps: { subtitle: "", note: "", variant: "hub-spoke" },
    render: renderSystemIntegration,
  },
  {
    id: "technical-diagram-v1",
    label: "DiagramSpec technical architecture, integration, or pipeline",
    editor: {
      label: "专业技术图",
      description: "DiagramSpec 节点/边可编辑，ELK 自动布局，PPTX 矢量导出",
      controls: {
        enums: {
          diagram_kind: {
            label: "技术图类型",
            options: {
              architecture: "架构图",
              integration: "系统集成图",
              pipeline: "数据管道",
            },
          },
          direction: {
            label: "布局方向",
            options: { RIGHT: "从左到右", DOWN: "从上到下" },
          },
        },
        diagramData: {
          label: "DiagramSpec",
          nodesPath: "nodes",
          edgesPath: "edges",
          minNodes: 2,
          maxNodes: 16,
          minEdges: 0,
          maxEdges: 24,
        },
      },
      defaultProps: {
        eyebrow: "技术架构",
        title: "企业 AI 服务平台架构",
        subtitle: "节点与连接关系可编辑；修改结构后重新执行自动布局",
        diagram_kind: "architecture",
        direction: "RIGHT",
        nodes: [
          { id: "channel", label: "用户渠道", detail: "Web · App · IM", kind: "client" },
          { id: "gateway", label: "API Gateway", detail: "鉴权 · 限流 · 路由", kind: "gateway" },
          { id: "orchestrator", label: "AI Orchestrator", detail: "会话 · 工具 · 策略", kind: "hub" },
          { id: "knowledge", label: "知识检索", detail: "RAG · 向量索引", kind: "service" },
          { id: "business", label: "业务服务", detail: "订单 · CRM · 工单", kind: "external" },
          { id: "governance", label: "治理与观测", detail: "审计 · 指标 · 告警", kind: "data" },
        ],
        edges: [
          { id: "edge-channel-gateway", source: "channel", target: "gateway", label: "HTTPS" },
          { id: "edge-gateway-ai", source: "gateway", target: "orchestrator", label: "请求" },
          { id: "edge-ai-knowledge", source: "orchestrator", target: "knowledge", label: "检索" },
          { id: "edge-ai-business", source: "orchestrator", target: "business", label: "工具调用" },
          { id: "edge-ai-governance", source: "orchestrator", target: "governance", label: "日志 / 指标" },
        ],
        note: "PPTX 中导出为单个 SVG 矢量对象；节点级编辑保留在 HTML / DiagramSpec。",
      },
    },
    roles: [
      "architecture",
      "system-design",
      "integration",
      "data-flow",
      "data-pipeline",
      "technology",
    ],
    density: "high",
    contentShape: ["diagram-spec", "nodes", "edges", "architecture", "pipeline"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The DiagramSpec SVG is the primary visual; keep the slide background quiet and structural.",
    }),
    capabilities: ["editable", "pptx-safe", "diagram", "svg-vector", "auto-layout"],
    variants: ["architecture", "integration", "pipeline"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(72, { role: "heading" }),
      subtitle: textField(140, { required: false, role: "caption" }),
      diagram_kind: enumField(["architecture", "integration", "pipeline"], "architecture"),
      direction: enumField(["RIGHT", "DOWN"], "RIGHT"),
      nodes: arrayField(2, 16, {
        id: textField(32, { editor: false, role: "label" }),
        label: textField(36, { role: "heading" }),
        detail: textField(64, { required: false, role: "body" }),
        kind: textField(16, { required: false, role: "label" }),
      }),
      edges: arrayField(0, 24, {
        id: textField(48, { editor: false, role: "label" }),
        source: textField(32, { role: "label" }),
        target: textField(32, { role: "label" }),
        label: textField(32, { required: false, role: "caption" }),
      }),
      note: textField(160, { required: false, role: "caption" }),
    },
    defaultProps: {
      subtitle: "",
      diagram_kind: "architecture",
      direction: "RIGHT",
      note: "",
    },
    render: renderTechnicalDiagram,
  },
  {
    id: "dashboard-overview-v1",
    label: "Qualitative management dashboard overview",
    editor: {
      label: "管理看板",
      description: "不虚构数值的指标域与管理闭环",
      controls: {
        enums: {
          variant: {
            label: "看板样式",
            options: { management: "管理视图", operations: "运营视图" },
          },
        },
        collections: {
          items: {
            label: "指标域",
            itemDefault: { label: "MONITOR", title: "新指标域", detail: "说明需要观察或优化的内容。" },
          },
        },
      },
      defaultProps: {
        eyebrow: "管理看板",
        title: "输入运营管理闭环结论",
        subtitle: "先定义可观察的指标域；真实数值接入后再切换为 KPI 或图表",
        items: [
          { label: "EFFICIENCY", title: "服务效率", detail: "会话量、响应时长与解决路径" },
          { label: "EXPERIENCE", title: "客户体验", detail: "满意度、投诉与异常会话" },
          { label: "ROUTING", title: "人机分流", detail: "机器人承接与人工转接结构" },
          { label: "KNOWLEDGE", title: "知识运营", detail: "命中、缺口与更新效果" },
          { label: "SYSTEM", title: "系统稳定", detail: "接口、服务与告警状态" },
        ],
        insight: "看板用于持续发现问题、分派任务并验证优化结果，不以示意数字冒充真实业绩。",
        variant: "management",
      },
    },
    roles: ["dashboard", "operations", "monitoring", "management"],
    density: "high",
    contentShape: ["dashboard", "metric-domains", "management-loop"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "Use the editable dashboard modules as the only visual until real KPI values are available.",
    }),
    capabilities: ["editable", "pptx-safe", "qualitative-dashboard"],
    variants: ["management", "operations"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      items: arrayField(4, 6, {
        label: textField(24, { required: false, role: "label" }),
        title: textField(36, { role: "heading" }),
        detail: textField(84, { role: "body" }),
      }),
      insight: textField(140, { required: false, role: "lead" }),
      variant: enumField(["management", "operations"], "management"),
    },
    defaultProps: { subtitle: "", insight: "", variant: "management" },
    render: renderDashboardOverview,
  },
  {
    id: "chart-bar-v1",
    label: "Editable categorical bar chart",
    editor: {
      label: "柱状图",
      description: "三到七组可编辑分类数据",
      controls: {
        enums: {
          variant: {
            label: "图表方向",
            options: { horizontal: "水平条形", columns: "垂直柱形" },
          },
        },
        collections: {
          items: {
            label: "数据项",
            itemDefault: { label: "新分类", value: "50", note: "" },
          },
        },
        itemData: {
          label: "图表数据",
          path: "items",
          columns: [
            { key: "label", label: "分类" },
            { key: "value", label: "数值", numeric: true },
            { key: "note", label: "说明" },
          ],
        },
      },
      defaultProps: {
        eyebrow: "数据对比",
        title: "输入图表想表达的结论",
        subtitle: "用分类数据支撑页面观点",
        series_label: "数值",
        items: [
          { label: "分类 A", value: "82", note: "" },
          { label: "分类 B", value: "64", note: "" },
          { label: "分类 C", value: "47", note: "" },
          { label: "分类 D", value: "31", note: "" },
        ],
        insight: "突出最值得关注的差异或排序结论。",
        source: "",
        variant: "horizontal",
      },
    },
    roles: ["chart", "bar-chart", "ranking", "distribution", "data-comparison"],
    density: "medium-high",
    contentShape: ["chart", "categorical-data", "ranking"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The editable chart is the primary visual; skip generated media and keep the background quiet.",
    }),
    capabilities: ["editable", "pptx-safe", "data", "chart-spec"],
    variants: ["horizontal", "columns"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      series_label: textField(32, { required: false, role: "label" }),
      items: arrayField(3, 7, {
        label: textField(40, { role: "label" }),
        value: textField(18, { role: "metric" }),
        note: textField(52, { required: false, role: "caption" }),
      }),
      insight: textField(140, { required: false, role: "lead" }),
      source: textField(100, { required: false, role: "caption" }),
      variant: enumField(["horizontal", "columns"], "horizontal"),
    },
    defaultProps: {
      subtitle: "",
      series_label: "",
      insight: "",
      source: "",
      variant: "horizontal",
    },
    render: renderBarChart,
  },
  {
    id: "chart-data-v1",
    label: "Editable animated multi-series chart",
    editor: {
      label: "动态图表",
      description: "七种图表、二到十二个分类、最多四个系列",
      controls: {
        enums: {
          chart_type: {
            label: "图表类型",
            options: {
              bar: "条形",
              column: "柱形",
              line: "折线",
              area: "面积",
              pie: "饼图",
              donut: "环图",
              radar: "雷达",
            },
          },
          stacked: {
            label: "系列关系",
            options: { off: "并列", on: "堆叠" },
          },
          legend: {
            label: "图例",
            options: { auto: "自动", on: "显示", off: "隐藏" },
          },
          show_values: {
            label: "数值标签",
            options: { auto: "自动", on: "显示", off: "隐藏" },
          },
          animation: {
            label: "播放动画",
            options: { on: "开启", off: "关闭" },
          },
        },
        chartData: {
          label: "图表数据",
          categoriesPath: "categories",
          seriesPath: "series",
          minCategories: 2,
          maxCategories: 12,
          minSeries: 1,
          maxSeries: 4,
        },
      },
      defaultProps: {
        eyebrow: "趋势与结构",
        title: "输入图表需要说明的核心结论",
        subtitle: "数据可编辑，播放时自动呈现动画",
        chart_type: "column",
        categories: ["Q1", "Q2", "Q3", "Q4"],
        series: [
          { name: "本期", values: ["42", "58", "71", "86"] },
          { name: "上期", values: ["34", "49", "57", "69"] },
        ],
        legend: "auto",
        show_values: "auto",
        animation: "on",
        stacked: "off",
        value_suffix: "",
        insight: "用一句话指出趋势、差距或结构变化。",
        source: "",
      },
    },
    roles: [
      "chart",
      "line-chart",
      "area-chart",
      "pie-chart",
      "donut-chart",
      "radar-chart",
      "trend",
      "distribution",
      "multi-series",
    ],
    density: "medium-high",
    contentShape: ["chart", "time-series", "categorical-data", "multi-series"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The editable animated chart is the primary visual; keep the background quiet and skip generated media.",
    }),
    capabilities: [
      "editable",
      "pptx-safe",
      "data",
      "chart-spec",
      "echarts-svg",
      "animation",
      "native-pptx-chart",
    ],
    variants: ["bar", "column", "line", "area", "pie", "donut", "radar"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(72, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      chart_type: enumField(["bar", "column", "line", "area", "pie", "donut", "radar"], "column"),
      categories: arrayField(2, 12, textField(28, { role: "label" })),
      series: arrayField(1, 4, {
        name: textField(32, { role: "label" }),
        values: arrayField(2, 12, textField(18, { role: "metric" })),
      }),
      legend: enumField(["auto", "on", "off"], "auto"),
      show_values: enumField(["auto", "on", "off"], "auto"),
      animation: enumField(["on", "off"], "on"),
      stacked: enumField(["off", "on"], "off"),
      value_suffix: textField(8, { required: false, role: "label" }),
      insight: textField(140, { required: false, role: "lead" }),
      source: textField(100, { required: false, role: "caption" }),
    },
    defaultProps: {
      subtitle: "",
      legend: "auto",
      show_values: "auto",
      animation: "on",
      stacked: "off",
      value_suffix: "",
      insight: "",
      source: "",
    },
    render: renderDataChart,
  },
  {
    id: "heatmap-matrix-v1",
    label: "Editable semantic heatmap matrix",
    editor: {
      label: "风险热力图",
      description: "三到六列、二到八行的可编辑热力矩阵",
      controls: {
        collections: {
          columns: { label: "列", itemDefault: "新列" },
          rows: { label: "行", itemDefault: ["新风险", "待补充", "待补充", "待补充"] },
        },
      },
      defaultProps: {
        eyebrow: "风险与优先级",
        title: "输入热力图要回答的决策问题",
        subtitle: "用颜色强度显示需要优先关注的区域",
        columns: ["风险域", "发生概率", "影响程度", "应对优先级"],
        rows: [
          ["风险一", "待补充", "待补充", "待补充"],
          ["风险二", "待补充", "待补充", "待补充"],
          ["风险三", "待补充", "待补充", "待补充"],
        ],
        low_label: "低",
        high_label: "高",
        insight: "",
        source: "",
      },
    },
    roles: ["heatmap", "risk-heatmap", "matrix", "risk-matrix", "priority-map"],
    density: "high",
    contentShape: ["heatmap", "matrix", "categorical-data", "risk-priority"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The editable heatmap is the primary visual; keep the background quiet and skip generated media.",
    }),
    capabilities: ["editable", "pptx-safe", "data", "matrix", "heatmap"],
    variants: ["semantic"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(72, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      columns: arrayField(3, 6, textField(36, { role: "label" })),
      rows: arrayField(2, 8, arrayField(3, 6, textField(48, { role: "body" }))),
      low_label: textField(16, { required: false, role: "label" }),
      high_label: textField(16, { required: false, role: "label" }),
      insight: textField(140, { required: false, role: "lead" }),
      source: textField(100, { required: false, role: "source" }),
    },
    defaultProps: {
      subtitle: "",
      low_label: "低",
      high_label: "高",
      insight: "",
      source: "",
    },
    render: renderHeatmapMatrix,
  },
  {
    id: "table-data-v1",
    label: "Editable two to six-column data table or Gantt matrix",
    editor: {
      label: "数据表格",
      description: "二到六列、二到十二行的结构化信息或甘特计划",
      controls: {
        enums: {
          variant: {
            label: "表格样式",
            options: { ledger: "横线表", comparison: "对比强调", gantt: "甘特计划" },
          },
        },
        collections: {
          columns: { label: "列", itemDefault: "新列" },
          rows: { label: "行", itemDefault: ["新项目", "—", "—"] },
        },
      },
      defaultProps: {
        eyebrow: "结构化信息",
        title: "输入需要精确比较的主题",
        subtitle: "当精确标签和值比趋势更重要时使用表格",
        columns: ["项目", "方案 A", "方案 B", "说明"],
        rows: [
          ["维度一", "已支持", "部分支持", "补充差异"],
          ["维度二", "高", "中", "补充差异"],
          ["维度三", "3 天", "7 天", "补充差异"],
        ],
        insight: "",
        source: "",
        variant: "ledger",
      },
    },
    roles: ["table", "data-table", "comparison-table", "matrix", "schedule", "gantt"],
    density: "high",
    contentShape: ["table", "exact-values", "matrix", "gantt-schedule"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "rare",
      textRegionNames: ["header", "content"],
      decisionRule: "The editable table is the primary visual; do not add generated imagery behind exact values.",
    }),
    capabilities: ["editable", "pptx-safe", "data", "table"],
    variants: ["ledger", "comparison", "gantt"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      columns: arrayField(2, 6, textField(36, { role: "label" })),
      rows: arrayField(2, 12, arrayField(2, 6, textField(48, { role: "body" }))),
      insight: textField(140, {
        required: false,
        role: "lead",
      }),
      source: textField(100, {
        required: false,
        role: "source",
      }),
      variant: enumField(["ledger", "comparison", "gantt"], "ledger"),
    },
    defaultProps: { subtitle: "", insight: "", source: "", variant: "ledger" },
    render: renderDataTable,
  },
  {
    id: "timeline-horizontal-v1",
    label: "Three to five-step timeline",
    editor: {
      label: "流程时间线",
      description: "三到五个连续阶段",
      controls: {
        enums: {
          variant: {
            label: "时间线样式",
            options: { horizontal: "水平", staggered: "错落" },
          },
        },
        collections: {
          steps: {
            label: "步骤",
            itemDefault: { phase: "新阶段", title: "新步骤", body: "说明这一阶段要完成什么。" },
          },
        },
      },
      defaultProps: {
        eyebrow: "路径",
        title: "输入流程标题",
        subtitle: "",
        steps: [
          { phase: "阶段 1", title: "第一步", body: "说明这一阶段要完成什么。" },
          { phase: "阶段 2", title: "第二步", body: "说明这一阶段要完成什么。" },
          { phase: "阶段 3", title: "第三步", body: "说明这一阶段要完成什么。" },
        ],
        variant: "horizontal",
      },
    },
    roles: ["timeline", "process", "roadmap", "journey"],
    density: "medium",
    contentShape: ["sequence", "steps"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "subtle",
      textRegionNames: ["header", "content"],
    }),
    capabilities: ["editable", "pptx-safe"],
    variants: ["horizontal", "staggered"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      subtitle: textField(120, { required: false, role: "caption" }),
      steps: arrayField(3, 5, {
        phase: textField(20, { required: false, role: "label" }),
        title: textField(32, { role: "heading" }),
        body: textField(90, { required: false, role: "body" }),
      }),
      variant: enumField(["horizontal", "staggered"], "horizontal"),
    },
    defaultProps: { subtitle: "", variant: "horizontal" },
    render: renderTimeline,
  },
  {
    id: "project-case-study-v1",
    label: "Project case study with visual and proof metrics",
    editor: {
      label: "项目案例",
      description: "主视觉、项目定位与两到三个证明指标",
      controls: {
        enums: {
          composition: {
            label: "案例构图",
            options: { split: "左右分栏", poster: "上下海报" },
          },
          media_side: {
            label: "图片位置",
            options: { left: "左侧", right: "右侧" },
          },
        },
        collections: {
          metrics: {
            label: "证明指标",
            itemDefault: { value: "待补充", label: "指标说明" },
          },
        },
      },
      defaultProps: {
        eyebrow: "项目案例",
        title: "品牌项目 A（待补充）",
        positioning: "用一句话说明项目所处情境、核心动作与设计角色。",
        image: { src: EDITOR_PLACEHOLDER_IMAGE, alt: "双击替换项目视觉" },
        metrics: [
          { value: "待补充", label: "项目指标" },
          { value: "待补充", label: "结果指标" },
        ],
        caption: "",
        composition: "split",
        media_side: "right",
      },
    },
    roles: ["case-study", "portfolio", "project", "results"],
    density: "medium",
    contentShape: ["project-story", "hero-media", "metrics"],
    mediaSlots: mediaSlots(0, 1, ["4:3", "16:9"], {
      backgroundMode: "rare",
      textRegionNames: ["project-copy", "project-metrics"],
      decisionRule: "Use a source-backed or generated project visual when available; otherwise keep the honest editable placeholder or select a non-media layout.",
      slots: [{
        id: "image",
        propPath: "image",
        role: "project-visual",
        required: false,
        strategies: ["generate", "use_existing", "skip"],
        preferredRatio: "4:3",
        placementControlledBy: "media_side",
      }],
    }),
    capabilities: ["editable", "pptx-safe", "generated-image", "data"],
    variants: ["split-left", "split-right", "poster"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(64, { role: "heading" }),
      positioning: textField(180, { role: "lead" }),
      image: mediaField({ required: false, aspectRatio: "4:3" }),
      metrics: arrayField(2, 3, {
        value: textField(24, { role: "metric-or-point" }),
        label: textField(36, { role: "caption" }),
      }),
      caption: textField(72, { required: false, role: "caption" }),
      composition: enumField(["split", "poster"], "split"),
      media_side: enumField(["left", "right"], "right"),
    },
    defaultProps: { caption: "", composition: "split", media_side: "right" },
    render: renderProjectCase,
  },
  {
    id: "image-hero-split-v1",
    label: "Image-led split story",
    editor: {
      label: "图文重点",
      description: "一张主图与一段核心叙事",
      controls: {
        enums: {
          media_side: {
            label: "图片位置",
            options: { left: "左侧", right: "右侧" },
          },
        },
      },
      defaultProps: {
        eyebrow: "案例",
        title: "输入图文标题",
        body: "用一段简洁叙述说明图片与主题之间的关系。",
        image: { src: EDITOR_PLACEHOLDER_IMAGE, alt: "双击替换图片" },
        caption: "",
        media_side: "right",
      },
    },
    roles: ["case-study", "product", "solution", "vision"],
    density: "medium-low",
    contentShape: ["story", "hero-media"],
    mediaSlots: mediaSlots(1, 1, ["4:3", "16:9"], {
      backgroundMode: "subtle",
      textRegionNames: ["image-copy"],
      decisionRule: "Resolve the required image from generation or a source-backed asset; never leave the slot unresolved.",
      slots: [{
        id: "image",
        propPath: "image",
        role: "story-visual",
        required: true,
        strategies: ["generate", "use_existing"],
        preferredRatio: "4:3",
        placementControlledBy: "media_side",
      }],
    }),
    capabilities: ["editable", "pptx-safe", "generated-image"],
    variants: ["media-left", "media-right"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(72, { role: "heading" }),
      body: textField(220, { role: "lead" }),
      image: mediaField({ required: true, aspectRatio: "4:3" }),
      caption: textField(72, { required: false, role: "caption" }),
      media_side: enumField(["left", "right"], "right"),
    },
    defaultProps: { caption: "", media_side: "right" },
    render: renderImageHero,
  },
  {
    id: "closing-next-steps-v1",
    label: "Closing statement with next steps or contact",
    editor: {
      label: "结尾页",
      description: "收束观点、后续动作与联系信息",
      controls: {
        enums: {
          variant: {
            label: "结尾构图",
            options: { "next-steps": "后续动作", contact: "联系收束" },
          },
        },
        collections: {
          actions: {
            label: "后续动作",
            itemDefault: { label: "下一步", detail: "说明需要继续推进的动作。" },
          },
        },
      },
      defaultProps: {
        eyebrow: "下一步",
        title: "让结论落到下一次行动",
        subtitle: "用一句话收束演示，并明确会后如何继续。",
        actions: [
          { label: "确认优先级", detail: "对齐最先启动的事项与负责人。" },
          { label: "安排复盘", detail: "约定下一次检查进展的时间。" },
        ],
        contact: "team@example.com",
        variant: "next-steps",
      },
    },
    roles: ["closing", "next-steps", "cta", "contact", "thank-you"],
    density: "medium-low",
    contentShape: ["closing-statement", "actions", "contact"],
    mediaSlots: mediaSlots(0, 0, [], {
      backgroundMode: "expressive",
      textRegionNames: ["closing-copy", "closing-actions"],
      decisionRule: "Use a generated or existing background only for an emotionally led close; otherwise let the final statement and actions carry the page.",
    }),
    capabilities: ["editable", "pptx-safe", "generated-background"],
    variants: ["next-steps", "contact"],
    fields: {
      eyebrow: textField(32, { role: "label" }),
      title: textField(84, { role: "display" }),
      subtitle: textField(180, { required: false, role: "lead" }),
      actions: arrayField(0, 4, {
        label: textField(36, { role: "heading" }),
        detail: textField(100, { role: "body" }),
      }),
      contact: textField(100, { required: false, role: "caption" }),
      variant: enumField(["next-steps", "contact"], "next-steps"),
    },
    defaultProps: { subtitle: "", actions: [], contact: "", variant: "next-steps" },
    render: renderClosing,
  },
];

layouts.forEach(layout => {
  const renderLayout = layout.render;
  layout.render = function renderCompositionAwareLayout(slide, index, design = null) {
    const previousDesign = activeCompositionDesign;
    activeCompositionDesign = normalizedCompositionDesign(design);
    try {
      return renderLayout(slide, index);
    } finally {
      activeCompositionDesign = previousDesign;
    }
  };
});

function contentUnit(value) {
  if (typeof value === "string") {
    return { label: "", title: value, body: value, value: "" };
  }
  if (Array.isArray(value)) {
    const cells = value.map(textValue).filter(Boolean);
    return cells.length
      ? { label: "", title: cells[0], body: cells.slice(1).join(" · "), value: cells[1] || "" }
      : null;
  }
  if (!value || typeof value !== "object") return null;
  return {
    label: firstText(value.kicker, value.label, value.phase, value.delta),
    title: firstText(value.title, value.value, value.label),
    body: firstText(
      value.body,
      value.detail,
      value.flow,
      Array.isArray(value.modules) ? value.modules.join(" · ") : "",
      value.footer,
      value.note,
      value.label
    ),
    value: firstText(value.value),
  };
}

function contentSnapshot(sourceSlide) {
  const props = sourceSlide && sourceSlide.props && typeof sourceSlide.props === "object"
    ? sourceSlide.props
    : {};
  const units = [];
  const addUnits = values => {
    if (!Array.isArray(values)) return;
    values.forEach(value => {
      const unit = contentUnit(value);
      if (unit && firstText(unit.title, unit.body, unit.value)) units.push(unit);
    });
  };

  addUnits(props.items);
  addUnits(props.steps);
  addUnits(props.proofs);
  addUnits(props.metrics);
  addUnits(props.sections);
  addUnits(props.actions);
  addUnits(props.layers);
  addUnits(props.systems);
  addUnits(props.nodes);
  addUnits(props.rows);
  if (Array.isArray(props.categories) && Array.isArray(props.series)) {
    const firstSeries = props.series.find(item => item && Array.isArray(item.values));
    props.categories.forEach((category, index) => {
      units.push({
        label: firstText(category),
        title: firstText(category),
        body: "",
        value: firstSeries ? firstText(firstSeries.values[index]) : "",
      });
    });
  }
  [props.left, props.right].forEach(side => {
    if (!side || typeof side !== "object" || !Array.isArray(side.items)) return;
    side.items.forEach(item => {
      units.push({
        label: firstText(side.label),
        title: firstText(item),
        body: firstText(side.title, side.footer),
        value: "",
      });
    });
  });

  const media = [props.hero, props.image]
    .find(value => value && typeof value === "object" && textValue(value.src));
  return {
    eyebrow: firstText(props.eyebrow),
    title: firstText(
      props.title,
      props.statement,
      props.number,
      props.left && props.left.title,
      props.right && props.right.title
    ),
    subtitle: firstText(props.subtitle, props.support, props.body, props.insight, props.caption, props.meta),
    number: firstText(props.number, props.marker),
    caption: firstText(props.caption, props.meta, props.contact, props.source),
    media: media ? deepClone(media) : null,
    units,
    props,
  };
}

function fillFromDefaults(items, defaults, minimum) {
  const result = items.slice();
  while (result.length < minimum) {
    result.push(deepClone(defaults[result.length % defaults.length]));
  }
  return result;
}

function createEditorProps(layoutId, sourceSlide = null) {
  const layout = getLayout(layoutId);
  if (!layout || !layout.editor || !layout.editor.defaultProps) return null;
  const props = deepClone(layout.editor.defaultProps);
  if (!sourceSlide) return props;

  const snapshot = contentSnapshot(sourceSlide);
  if (Object.prototype.hasOwnProperty.call(props, "eyebrow") && snapshot.eyebrow) {
    props.eyebrow = fitText(snapshot.eyebrow, layout.fields.eyebrow.maxChars, props.eyebrow);
  }
  if (Object.prototype.hasOwnProperty.call(props, "title") && snapshot.title) {
    props.title = fitText(snapshot.title, layout.fields.title.maxChars, props.title);
  }
  if (Object.prototype.hasOwnProperty.call(props, "subtitle") && snapshot.subtitle) {
    props.subtitle = fitText(snapshot.subtitle, layout.fields.subtitle.maxChars, props.subtitle);
  }

  if (layoutId === "cover-hero-v1") {
    if (snapshot.caption) props.meta = fitText(snapshot.caption, 64, props.meta);
    if (snapshot.media) props.hero = snapshot.media;
  } else if (layoutId === "cover-editorial-v1") {
    if (snapshot.number) props.marker = fitText(snapshot.number, 24, props.marker);
    if (snapshot.caption) props.meta = fitText(snapshot.caption, 72, props.meta);
  } else if (layoutId === "section-marker-v1") {
    if (snapshot.number) props.number = fitText(snapshot.number, 8, props.number);
  } else if (layoutId === "statement-focus-v1") {
    if (snapshot.title) props.statement = fitText(snapshot.title, 120, props.statement);
    if (snapshot.subtitle) props.support = fitText(snapshot.subtitle, 180, props.support);
    if (snapshot.units.length) {
      props.proofs = snapshot.units.slice(0, 3).map((unit, index) => ({
        value: fitText(firstText(unit.value, unit.title, unit.body), 36, `要点 ${index + 1}`),
        label: fitText(firstText(unit.label, unit.body, unit.title), 52, "证明点"),
      }));
    }
  } else if (layoutId === "cards-grid-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 6).map((unit, index) => ({
      kicker: fitText(unit.label, 24, String(index + 1).padStart(2, "0")),
      title: fitText(firstText(unit.title, unit.value), 36, `要点 ${index + 1}`),
      body: fitText(firstText(unit.body, unit.title, unit.value), 100, "补充说明"),
    }));
    props.items = fillFromDefaults(mapped, props.items, 3);
  } else if (layoutId === "text-columns-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 3).map((unit, index) => ({
      label: fitText(unit.label, 24, String(index + 1).padStart(2, "0")),
      title: fitText(firstText(unit.title, unit.value), 40, `主题 ${index + 1}`),
      body: fitText(firstText(unit.body, unit.title, unit.value), 180, "补充完整说明。"),
      bullets: [],
    }));
    props.sections = fillFromDefaults(mapped, props.sections, 2);
  } else if (layoutId === "comparison-two-column-v1" && snapshot.units.length) {
    const items = snapshot.units.slice(0, 10).map(unit =>
      fitText(firstText(unit.title, unit.body, unit.value), 72, "输入对比点")
    );
    const splitAt = Math.max(1, Math.ceil(items.length / 2));
    props.left.items = fillFromDefaults(items.slice(0, splitAt), props.left.items, 2).slice(0, 5);
    props.right.items = fillFromDefaults(items.slice(splitAt), props.right.items, 2).slice(0, 5);
    if (snapshot.props.left && snapshot.props.left.title) {
      props.left.title = fitText(snapshot.props.left.title, 42, props.left.title);
    }
    if (snapshot.props.right && snapshot.props.right.title) {
      props.right.title = fitText(snapshot.props.right.title, 42, props.right.title);
    }
  } else if (layoutId === "kpi-grid-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 6).map((unit, index) => {
      const candidate = firstText(unit.value, unit.title);
      return {
        label: fitText(firstText(unit.label, unit.title), 36, `指标 ${index + 1}`),
        value: fitText(isCompactMetric(candidate) ? candidate : String(index + 1).padStart(2, "0"), 18),
        detail: fitText(firstText(unit.body, unit.title, unit.value), 90, "补充数据说明"),
        delta: "",
      };
    });
    props.items = fillFromDefaults(mapped, props.items, 3);
  } else if (layoutId === "architecture-layered-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 5).map((unit, index) => ({
      label: fitText(unit.label, 24, `LAYER ${index + 1}`),
      title: fitText(firstText(unit.title, unit.value), 36, `架构层 ${index + 1}`),
      modules: [fitText(firstText(unit.body, unit.title), 28, "待补充模块"), "待补充模块"],
    }));
    props.layers = fillFromDefaults(mapped, props.layers, 3);
  } else if (layoutId === "system-integration-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 8).map((unit, index) => ({
      title: fitText(firstText(unit.title, unit.value), 32, `系统 ${index + 1}`),
      flow: fitText(firstText(unit.body, unit.label), 64, "输入交换的数据或动作"),
    }));
    props.systems = fillFromDefaults(mapped, props.systems, 4);
  } else if (layoutId === "technical-diagram-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 12).map((unit, index) => ({
      id: `node-${index + 1}`,
      label: fitText(firstText(unit.title, unit.value), 36, `节点 ${index + 1}`),
      detail: fitText(firstText(unit.body, unit.label), 64, ""),
      kind: index === 0 ? "client" : index === snapshot.units.length - 1 ? "data" : "service",
    }));
    props.nodes = fillFromDefaults(mapped, props.nodes, 2);
    props.edges = props.nodes.slice(1).map((node, index) => ({
      id: `edge-${index + 1}`,
      source: props.nodes[index].id,
      target: node.id,
      label: "",
    }));
    if (sourceSlide.layout_id === "system-integration-v1") {
      props.diagram_kind = "integration";
      props.direction = "RIGHT";
    } else if (sourceSlide.layout_id === "architecture-layered-v1") {
      props.diagram_kind = "architecture";
      props.direction = "DOWN";
    }
  } else if (layoutId === "dashboard-overview-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 6).map((unit, index) => ({
      label: fitText(unit.label, 24, `DOMAIN ${index + 1}`),
      title: fitText(firstText(unit.title, unit.value), 36, `指标域 ${index + 1}`),
      detail: fitText(firstText(unit.body, unit.title), 84, "说明需要观察或优化的内容。"),
    }));
    props.items = fillFromDefaults(mapped, props.items, 4);
  } else if (layoutId === "chart-bar-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 7).map((unit, index) => {
      const candidate = firstText(unit.value, unit.title);
      const fallbackValue = String(Math.max(10, 90 - index * 14));
      return {
        label: fitText(firstText(unit.label, unit.title, unit.body), 40, `分类 ${index + 1}`),
        value: fitText(/\d/.test(candidate) ? candidate : fallbackValue, 18, fallbackValue),
        note: fitText(firstText(unit.body), 52, ""),
      };
    });
    props.items = fillFromDefaults(mapped, props.items, 3);
  } else if (layoutId === "chart-data-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 12);
    props.categories = fillFromDefaults(
      mapped.map((unit, index) => fitText(firstText(unit.label, unit.title), 28, `分类 ${index + 1}`)),
      props.categories,
      2
    );
    props.series = [{
      name: firstText(snapshot.props.series_label, "数值"),
      values: props.categories.map((_, index) => {
        const candidate = mapped[index] && firstText(mapped[index].value, mapped[index].title);
        return fitText(candidate && /\d/.test(candidate) ? candidate : String(30 + index * 12), 18);
      }),
    }];
  } else if (layoutId === "heatmap-matrix-v1") {
    if (Array.isArray(snapshot.props.columns) && Array.isArray(snapshot.props.rows)) {
      props.columns = snapshot.props.columns.slice(0, 6).map(value => fitText(value, 36, "新列"));
      props.rows = snapshot.props.rows.slice(0, 8).map(row =>
        (Array.isArray(row) ? row : []).slice(0, 6).map(value => fitText(value, 48, "待补充"))
      );
      props.rows = fillFromDefaults(
        props.rows,
        props.rows.length ? props.rows : [["新风险", "待补充", "待补充"]],
        2
      );
    }
  } else if (layoutId === "table-data-v1") {
    if (Array.isArray(snapshot.props.columns) && Array.isArray(snapshot.props.rows)) {
      props.columns = snapshot.props.columns.slice(0, 6).map(value => fitText(value, 36, "新列"));
      props.rows = snapshot.props.rows.slice(0, 12).map(row =>
        (Array.isArray(row) ? row : []).slice(0, 6).map(value => fitText(value, 48, "—"))
      );
      props.rows = fillFromDefaults(props.rows, props.rows.length ? props.rows : [["项目", "—"]], 2);
    } else if (snapshot.units.length) {
      props.columns = ["项目", "数值 / 内容", "说明"];
      const mapped = snapshot.units.slice(0, 12).map((unit, index) => [
        fitText(firstText(unit.label, unit.title), 48, `项目 ${index + 1}`),
        fitText(firstText(unit.value, unit.title), 48, "—"),
        fitText(firstText(unit.body), 48, "—"),
      ]);
      props.rows = fillFromDefaults(mapped, props.rows, 2);
    }
  } else if (layoutId === "timeline-horizontal-v1" && snapshot.units.length) {
    const mapped = snapshot.units.slice(0, 5).map((unit, index) => ({
      phase: fitText(unit.label, 20, `阶段 ${index + 1}`),
      title: fitText(firstText(unit.title, unit.value), 32, `第 ${index + 1} 步`),
      body: fitText(firstText(unit.body, unit.title, unit.value), 90, "说明这一阶段要完成什么。"),
    }));
    props.steps = fillFromDefaults(mapped, props.steps, 3);
  } else if (layoutId === "project-case-study-v1") {
    if (snapshot.subtitle) {
      props.positioning = fitText(snapshot.subtitle, 180, props.positioning);
    }
    if (snapshot.caption) props.caption = fitText(snapshot.caption, 72, props.caption);
    if (snapshot.media) props.image = snapshot.media;
    if (snapshot.units.length) {
      const mapped = snapshot.units.slice(0, 3).map((unit, index) => ({
        value: fitText(firstText(unit.value, unit.title), 24, "待补充"),
        label: fitText(firstText(unit.label, unit.body, unit.title), 36, `指标 ${index + 1}`),
      }));
      props.metrics = fillFromDefaults(mapped, props.metrics, 2);
    }
  } else if (layoutId === "image-hero-split-v1") {
    if (snapshot.subtitle) props.body = fitText(snapshot.subtitle, 220, props.body);
    if (snapshot.caption) props.caption = fitText(snapshot.caption, 72, props.caption);
    if (snapshot.media) props.image = snapshot.media;
  } else if (layoutId === "closing-next-steps-v1") {
    if (snapshot.caption) props.contact = fitText(snapshot.caption, 100, props.contact);
    if (snapshot.units.length) {
      props.actions = snapshot.units.slice(0, 3).map((unit, index) => ({
        label: fitText(firstText(unit.title, unit.label), 36, `下一步 ${index + 1}`),
        detail: fitText(firstText(unit.body, unit.value, unit.title), 100, "补充后续动作。"),
      }));
    }
  }

  return props;
}

function getLayout(layoutId) {
  return layouts.find(layout => layout.id === layoutId) || null;
}

function manifestRecord(layout) {
  const { render, ...record } = layout;
  return record;
}

return {
  EDITOR_PLACEHOLDER_IMAGE,
  createEditorProps,
  createTechnicalDiagramPreset,
  escapeHtml,
  getLayout,
  layouts,
  manifestRecord,
};
});
