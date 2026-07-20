#!/usr/bin/env node
"use strict";

const fs = require("fs");
const Module = require("module");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");
const {
  chromiumLaunchOptions,
  ensurePlaywrightBrowsersPath,
} = require("./playwright_host");
const { resolveArtifactPath } = require("./deck_spec_core.js");

function usage() {
  console.error("Usage: probe_deck_runtime.js index.html [--viewport WxH] [--report qa/runtime_probe.json]");
  process.exit(2);
}

function parseViewport(value) {
  const match = /^(\d+)\s*[xX]\s*(\d+)$/.exec(String(value || ""));
  if (!match) return null;
  return { width: Number(match[1]), height: Number(match[2]) };
}

function parseArgs(argv) {
  if (!argv[0] || argv[0] === "--help" || argv[0] === "-h") usage();
  const opts = {
    html: resolveArtifactPath(argv[0]),
    viewport: { width: 1440, height: 900 },
    report: null,
  };
  for (let index = 1; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (arg === "--viewport" && value) {
      const viewport = parseViewport(value);
      if (!viewport) usage();
      opts.viewport = viewport;
      index += 1;
    } else if (arg === "--report" && value) {
      opts.report = resolveArtifactPath(value);
      index += 1;
    } else {
      usage();
    }
  }
  return opts;
}

function officeRaccoonPrefix() {
  if (process.env.BOX_AGENT_NODE_PREFIX) return process.env.BOX_AGENT_NODE_PREFIX;
  if (process.env.BOX_AGENT_RUNTIME_PREFIX) return process.env.BOX_AGENT_RUNTIME_PREFIX;
  const home = os.homedir();
  if (process.platform === "darwin") {
    return path.join(home, "Library", "Application Support", "office-raccoon");
  }
  if (process.platform === "win32") {
    return path.join(process.env.APPDATA || home, "office-raccoon");
  }
  return path.join(home, ".config", "office-raccoon");
}

function loadPlaywright() {
  ensurePlaywrightBrowsersPath();
  const managedNodeModules = path.join(officeRaccoonPrefix(), "node_modules");
  process.env.NODE_PATH = process.env.NODE_PATH
    ? `${managedNodeModules}${path.delimiter}${process.env.NODE_PATH}`
    : managedNodeModules;
  Module._initPaths();
  return require("playwright");
}

async function readEditorState(page, viewport) {
  return page.evaluate(({ width, height }) => {
    function rgb(value) {
      const match = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(value || "");
      return match ? match.slice(1, 4).map(Number) : null;
    }
    function luminance(color) {
      if (!color) return null;
      const channels = color.map(value => {
        const normalized = value / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2]);
    }
    function contrast(foreground, background) {
      const left = luminance(rgb(foreground));
      const right = luminance(rgb(background));
      if (left == null || right == null) return null;
      return (Math.max(left, right) + 0.05) / (Math.min(left, right) + 0.05);
    }

    const firstSlide = document.querySelector("#deck-root > .slide");
    const toolbar = document.querySelector(".deck-toolbar");
    const statement = document.querySelector(".statement-poster");
    const firstRect = firstSlide && firstSlide.getBoundingClientRect();
    const toolbarRect = toolbar && toolbar.getBoundingClientRect();
    const statementStyle = statement && getComputedStyle(statement);
    const rootStyle = getComputedStyle(document.documentElement);
    return {
      viewport: { width, height },
      bodyOverflowX: getComputedStyle(document.body).overflowX,
      thumbnailsVisible: document.body.classList.contains("deck-thumbnails-visible"),
      editorScale: Number(rootStyle.getPropertyValue("--deck-editor-scale")) || 1,
      primary: rootStyle.getPropertyValue("--deck-primary").trim(),
      inverse: rootStyle.getPropertyValue("--deck-inverse").trim(),
      firstSlide: firstRect ? {
        left: firstRect.left,
        right: firstRect.right,
        top: firstRect.top,
        bottom: firstRect.bottom,
        width: firstRect.width,
        height: firstRect.height,
      } : null,
      toolbarTop: toolbarRect ? toolbarRect.top : null,
      toolbar: toolbarRect ? {
        left: toolbarRect.left,
        right: toolbarRect.right,
        width: toolbarRect.width,
        clientWidth: toolbar.clientWidth,
        scrollWidth: toolbar.scrollWidth,
        overflowX: getComputedStyle(toolbar).overflowX,
        hasOverflow: toolbar.scrollWidth > toolbar.clientWidth + 1,
      } : null,
      statement: statementStyle ? {
        background: statementStyle.backgroundColor,
        color: statementStyle.color,
        contrast: contrast(statementStyle.color, statementStyle.backgroundColor),
      } : null,
    };
  }, viewport);
}

async function probeToolbarMenuTrajectory(page, menuName) {
  const group = page.locator(`[data-toolbar-menu="${menuName}"]`);
  const trigger = group.locator("[data-toolbar-menu-trigger]");
  const menu = group.locator("[role=menu]");
  if (await group.count() === 0 || await trigger.count() === 0 || await menu.count() === 0) {
    return { available: false, open: false, expanded: false };
  }

  await page.mouse.move(8, 8);
  await page.waitForTimeout(220);
  await trigger.hover();
  const triggerBox = await trigger.boundingBox();
  const menuBox = await menu.boundingBox();
  if (!triggerBox || !menuBox) {
    return { available: true, open: false, expanded: false };
  }

  const start = {
    x: triggerBox.x + (triggerBox.width / 2),
    y: triggerBox.y + 2,
  };
  const end = {
    x: menuBox.x + 12,
    y: menuBox.y + menuBox.height - 2,
  };
  for (let step = 0; step <= 14; step += 1) {
    const ratio = step / 14;
    await page.mouse.move(
      start.x + ((end.x - start.x) * ratio),
      start.y + ((end.y - start.y) * ratio)
    );
    await page.waitForTimeout(20);
  }
  await page.waitForTimeout(40);

  return group.evaluate(element => {
    const menuTrigger = element.querySelector("[data-toolbar-menu-trigger]");
    return {
      available: true,
      open: element.classList.contains("is-open"),
      expanded: menuTrigger && menuTrigger.getAttribute("aria-expanded") === "true",
    };
  });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!fs.existsSync(opts.html)) throw new Error(`HTML file not found: ${opts.html}`);
  const { chromium } = loadPlaywright();
  const launch = chromiumLaunchOptions(chromium, { headless: true });
  const browser = await chromium.launch(launch.options);
  try {
    const context = await browser.newContext({ viewport: opts.viewport });
    await context.addInitScript(() => {
      Object.defineProperty(navigator, "webdriver", { configurable: true, get: () => false });
    });
    const page = await context.newPage();
    const editorUrl = pathToFileURL(opts.html).href;
    await page.goto(editorUrl, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => Boolean(window.__deckRuntime));
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const editor = await readEditorState(page, opts.viewport);
    editor.toolbarMenus = {
      design: await probeToolbarMenuTrajectory(page, "design"),
      page: await probeToolbarMenuTrajectory(page, "page"),
    };
    await context.close();

    const exportPage = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    const exportUrl = new URL(pathToFileURL(opts.html).href);
    exportUrl.searchParams.set("mode", "export");
    await exportPage.goto(exportUrl.href, { waitUntil: "domcontentloaded" });
    const exported = await exportPage.evaluate(() => {
      const slide = document.querySelector("#deck-root > .slide");
      const style = slide && getComputedStyle(slide);
      const rect = slide && slide.getBoundingClientRect();
      return slide ? {
        cssWidth: parseFloat(style.width),
        cssHeight: parseFloat(style.height),
        renderedWidth: rect.width,
        renderedHeight: rect.height,
      } : null;
    });
    await exportPage.close();

    const issues = [];
    if (!editor.firstSlide) issues.push("No slide found in editor mode");
    if (editor.firstSlide && (
      editor.firstSlide.left < -1 || editor.firstSlide.right > opts.viewport.width + 1
    )) {
      issues.push("Editor slide exceeds the horizontal viewport");
    }
    if (editor.firstSlide && editor.toolbarTop != null && editor.firstSlide.bottom > editor.toolbarTop + 1) {
      issues.push("Editor slide is obscured by the bottom toolbar");
    }
    if (editor.toolbar && (
      editor.toolbar.left < -1 || editor.toolbar.right > opts.viewport.width + 1
    )) {
      issues.push("Editor toolbar exceeds the horizontal viewport");
    }
    if (editor.toolbar && editor.toolbar.hasOverflow) {
      issues.push(
        `Editor toolbar overflows horizontally: ${editor.toolbar.scrollWidth}px > ${editor.toolbar.clientWidth}px`
      );
    }
    Object.entries(editor.toolbarMenus || {}).forEach(([menuName, state]) => {
      if (state.available && (!state.open || !state.expanded)) {
        issues.push(`Toolbar ${menuName} menu closes during pointer transition`);
      }
    });
    if (editor.statement && editor.statement.contrast < 4.5) {
      issues.push(`Statement contrast is too low: ${editor.statement.contrast.toFixed(2)}`);
    }
    if (!exported || exported.cssWidth !== 1920 || exported.cssHeight !== 1080) {
      issues.push("Export mode does not preserve the 1920x1080 CSS canvas");
    }
    if (!exported || exported.renderedWidth !== 1920 || exported.renderedHeight !== 1080) {
      issues.push("Export mode unexpectedly scales the slide canvas");
    }

    const report = { ok: issues.length === 0, issues, editor, export: exported };
    const output = `${JSON.stringify(report, null, 2)}\n`;
    if (opts.report) {
      fs.mkdirSync(path.dirname(opts.report), { recursive: true });
      fs.writeFileSync(opts.report, output, "utf8");
    }
    process.stdout.write(output);
    if (!report.ok) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
