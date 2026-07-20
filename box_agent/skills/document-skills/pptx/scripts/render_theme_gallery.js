#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const { createEditorProps } = require("../layouts/registry.js");
const {
  createDeckDesign,
  getTheme,
  listThemes,
  resolveArtifactPath,
  themeManifestRecord,
  validateAndNormalizeDeck,
} = require("./deck_spec_core.js");
const { renderDocument } = require("./render_deck_html.js");

const DEFAULT_PREVIEW_THEME_IDS = Object.freeze([
  "blue-professional",
  "signal",
  "biennale-yellow",
  "studio",
  "daisy-days",
  "block-frame-mono-blue",
  "retro-windows",
  "soft-editorial",
]);

function parseArgs(argv) {
  const opts = {
    out: "theme-previews/index.html",
    themeIds: null,
    all: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: render_theme_gallery.js [--out theme-previews/index.html] " +
        "[--themes id,id,... | --all]"
      );
      process.exit(0);
    }
    if (arg === "--out" && value) {
      opts.out = value;
      index += 1;
    } else if (arg === "--themes" && value) {
      opts.themeIds = value.split(",").map(item => item.trim()).filter(Boolean);
      index += 1;
    } else if (arg === "--all") {
      opts.all = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (opts.all && opts.themeIds) throw new Error("Use either --themes or --all, not both");
  return opts;
}

function truncate(value, maxChars) {
  return Array.from(String(value || "")).slice(0, maxChars).join("");
}

function previewDeck(theme) {
  const manifest = themeManifestRecord(theme);
  const cover = createEditorProps("cover-editorial-v1");
  Object.assign(cover, {
    eyebrow: "THEME PREVIEW",
    title: truncate(theme.name || theme.id, 84),
    subtitle: truncate(theme.description || "内置受控主题预览", 160),
    marker: "01",
    meta: truncate(`${theme.id} · ${manifest.composition.family}`, 72),
  });

  const cards = createEditorProps("cards-grid-v1");
  Object.assign(cards, {
    eyebrow: "VISUAL LANGUAGE",
    title: "同一内容，不同视觉语言",
    subtitle: "查看字体、色彩、表面与构图节奏如何协同工作。",
    items: [
      { kicker: "01", title: "核心观点", body: "让主题先建立识别度，再承载具体叙事。" },
      { kicker: "02", title: "信息层级", body: "标题、正文和标签保持清晰的阅读顺序。" },
      { kicker: "03", title: "视觉节奏", body: "用结构变化组织页面，而不是只替换颜色。" },
    ],
  });

  const chart = createEditorProps("chart-data-v1");
  Object.assign(chart, {
    eyebrow: "DATA PREVIEW",
    title: "数据页也继承同一主题",
    subtitle: "图表保持可编辑数据与统一视觉语法。",
    categories: ["策略", "设计", "内容", "交付"],
    series: [
      { name: "当前", values: ["42", "58", "66", "74"] },
      { name: "目标", values: ["68", "76", "84", "92"] },
    ],
    chart_type: "column",
    insight: "主题会影响图表色板与页面构图，但不会牺牲数据可编辑性。",
    source: "示意数据",
  });

  return {
    schema_version: 1,
    title: `${theme.name || theme.id} theme preview`,
    theme_id: theme.id,
    design: createDeckDesign(theme, `preview-${theme.id}`),
    slides: [
      { id: "preview-cover", layout_id: "cover-editorial-v1", props: cover },
      { id: "preview-content", layout_id: "cards-grid-v1", props: cards },
      { id: "preview-chart", layout_id: "chart-data-v1", props: chart },
    ],
  };
}

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function galleryDocument(themes) {
  const cards = themes.map(theme => {
    const manifest = themeManifestRecord(theme);
    const moods = Array.isArray(manifest.selection.mood_keywords)
      ? manifest.selection.mood_keywords.slice(0, 3).join(" · ")
      : "";
    const fileName = `${theme.id}.html`;
    return [
      '<article class="theme-card">',
      '  <div class="preview-stage">',
      `    <iframe src="./${escapeHtml(fileName)}?mode=gallery" title="${escapeHtml(theme.name || theme.id)} 主题预览" loading="lazy"></iframe>`,
      "  </div>",
      '  <div class="theme-copy">',
      `    <p class="family">${escapeHtml(manifest.composition.family)}</p>`,
      `    <h2>${escapeHtml(theme.name || theme.id)}</h2>`,
      `    <code>${escapeHtml(theme.id)}</code>`,
      `    <p class="description">${escapeHtml(theme.description || "")}</p>`,
      `    <p class="moods">${escapeHtml(moods)}</p>`,
      `    <a href="./${escapeHtml(fileName)}?mode=export" target="_blank" rel="noreferrer">打开 3 页完整预览 →</a>`,
      "  </div>",
      "</article>",
    ].join("\n");
  }).join("\n");

  return [
    "<!doctype html>",
    '<html lang="zh-CN">',
    "<head>",
    '  <meta charset="utf-8" />',
    '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
    '  <link rel="icon" href="data:," />',
    "  <title>PPT 内置主题预览</title>",
    "  <style>",
    "    :root { color-scheme: light; font-family: Inter, Aptos, Arial, 'PingFang SC', sans-serif; color: #161616; background: #f2f1ed; }",
    "    * { box-sizing: border-box; }",
    "    body { margin: 0; padding: 48px; }",
    "    header { max-width: 1040px; margin: 0 auto 36px; }",
    "    .kicker { margin: 0 0 12px; font-size: 13px; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; color: #575752; }",
    "    h1 { margin: 0; font-size: clamp(36px, 5vw, 72px); line-height: .98; letter-spacing: -.045em; }",
    "    .intro { max-width: 760px; margin: 20px 0 0; color: #555550; font-size: 18px; line-height: 1.55; }",
    "    .instruction { margin: 16px 0 0; padding-left: 14px; border-left: 3px solid #202020; font-weight: 650; }",
    "    .gallery { width: min(1500px, 100%); margin: 0 auto; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 28px; }",
    "    .theme-card { overflow: hidden; border: 1px solid #c9c8c2; background: #fff; }",
    "    .preview-stage { position: relative; aspect-ratio: 16 / 9; overflow: hidden; background: #d8d8d2; }",
    "    iframe { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; border: 0; transform: scale(.25); transform-origin: top left; pointer-events: none; }",
    "    .theme-copy { padding: 22px 24px 24px; }",
    "    .family { margin: 0 0 8px; color: #676762; font-size: 12px; font-weight: 750; letter-spacing: .1em; text-transform: uppercase; }",
    "    h2 { display: inline; margin: 0 12px 0 0; font-size: 25px; letter-spacing: -.025em; }",
    "    code { color: #666; font-size: 13px; }",
    "    .description { min-height: 48px; margin: 14px 0 0; color: #444; line-height: 1.5; }",
    "    .moods { min-height: 20px; margin: 10px 0 18px; color: #777; font-size: 13px; }",
    "    a { color: #111; font-weight: 700; text-underline-offset: 4px; }",
    "    @media (max-width: 980px) { body { padding: 28px 18px; } .gallery { grid-template-columns: 1fr; } }",
    "  </style>",
    "</head>",
    "<body>",
    "  <header>",
    '    <p class="kicker">Built-in controlled themes</p>',
    "    <h1>先看主题，再开始做 PPT</h1>",
    `    <p class="intro">这里展示 ${themes.length} 个代表性内置主题。每个主题都使用真实受控渲染器生成，包含自己的色彩、字体、视觉语法与 HTML 构图家族。</p>`,
    '    <p class="instruction">看完后，回复卡片上的 theme_id；如果都不合适，也可以描述你想要的气质。</p>',
    "  </header>",
    `  <main class="gallery">${cards}</main>`,
    "  <script>",
    "    (() => {",
    "      const fit = stage => {",
    "        const frame = stage.querySelector('iframe');",
    "        if (frame) frame.style.transform = `scale(${stage.clientWidth / 1920})`;",
    "      };",
    "      const stages = Array.from(document.querySelectorAll('.preview-stage'));",
    "      stages.forEach(fit);",
    "      if (window.ResizeObserver) {",
    "        const observer = new ResizeObserver(entries => entries.forEach(entry => fit(entry.target)));",
    "        stages.forEach(stage => observer.observe(stage));",
    "      } else {",
    "        window.addEventListener('resize', () => stages.forEach(fit));",
    "      }",
    "    })();",
    "  </script>",
    "</body>",
    "</html>",
    "",
  ].join("\n");
}

function selectedThemes(opts) {
  const ids = opts.all
    ? listThemes().map(theme => theme.id)
    : opts.themeIds || DEFAULT_PREVIEW_THEME_IDS;
  const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
  if (duplicates.length) throw new Error(`Duplicate theme id(s): ${[...new Set(duplicates)].join(", ")}`);
  return ids.map(id => {
    const theme = getTheme(id);
    if (!theme) throw new Error(`Unknown theme_id: ${JSON.stringify(id)}`);
    return theme;
  });
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const outputPath = resolveArtifactPath(opts.out);
  if (!/\.html?$/i.test(outputPath)) throw new Error("--out must name an .html file");
  const outputDir = path.dirname(outputPath);
  const themes = selectedThemes(opts);
  fs.mkdirSync(outputDir, { recursive: true });

  themes.forEach(theme => {
    const result = validateAndNormalizeDeck(previewDeck(theme));
    if (!result.ok) {
      throw new Error(`${theme.id} preview is invalid:\n- ${result.issues.join("\n- ")}`);
    }
    fs.writeFileSync(
      path.join(outputDir, `${theme.id}.html`),
      renderDocument(result.normalized, theme),
      "utf8"
    );
  });
  fs.writeFileSync(outputPath, galleryDocument(themes), "utf8");
  console.log(JSON.stringify({
    gallery: outputPath,
    theme_count: themes.length,
    themes: themes.map(theme => theme.id),
  }, null, 2));
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  }
}

module.exports = {
  DEFAULT_PREVIEW_THEME_IDS,
  galleryDocument,
  previewDeck,
};
