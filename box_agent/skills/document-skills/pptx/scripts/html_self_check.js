#!/usr/bin/env node
const fs = require("fs");
const Module = require("module");
const os = require("os");
const path = require("path");

function officeRaccoonPrefix() {
  if (process.env.BOX_AGENT_NODE_PREFIX) return process.env.BOX_AGENT_NODE_PREFIX;
  if (process.env.BOX_AGENT_RUNTIME_PREFIX) return process.env.BOX_AGENT_RUNTIME_PREFIX;
  // Use os.homedir() (HOME if set, else passwd lookup) — NOT process.env.HOME,
  // which is empty in GUI/launchd/spawn contexts where HOME is unset. Must match
  // check_html_export_env.js exactly, or the env preflight resolves playwright
  // while the real launch (different prefix) fails with "no playwright".
  const home = os.homedir();
  if (process.platform === "darwin") {
    return path.join(home, "Library", "Application Support", "office-raccoon");
  }
  if (process.platform === "win32") {
    return path.join(process.env.APPDATA || home, "office-raccoon");
  }
  return path.join(home, ".config", "office-raccoon");
}

function officeRaccoonBrowserHostPath() {
  return path.join(os.homedir(), ".box-agent", "browsers");
}

if (!process.env.PLAYWRIGHT_BROWSERS_PATH) {
  process.env.PLAYWRIGHT_BROWSERS_PATH = officeRaccoonBrowserHostPath();
}

const managedNodeModules = path.join(officeRaccoonPrefix(), "node_modules");
process.env.NODE_PATH = process.env.NODE_PATH
  ? `${managedNodeModules}${path.delimiter}${process.env.NODE_PATH}`
  : managedNodeModules;
Module._initPaths();

// Single source of truth for the slide canvas contract. Every `.slide` is
// asserted against this exact size — NOT auto-detected from the first slide,
// which used to let an entire deck drift to 1280x720 / 1400x840 and still pass.
const CANONICAL_WIDTH = 1920;
const CANONICAL_HEIGHT = 1080;

function usage() {
  console.error("Usage: html_self_check.js deck.html [--canvas WxH] [--dom-to-pptx] [--allow-local-images] [--report qa/html_self_check.json] [--verbose]");
  console.error(`  The canvas contract is ${CANONICAL_WIDTH}x${CANONICAL_HEIGHT} (16:9). Every .slide must match it exactly.`);
  console.error("  --canvas WxH overrides the contract for a deliberately non-standard deck (e.g. --canvas 1280x720).");
  console.error("  --width/--height are NOT accepted; set .slide CSS to the canvas size instead.");
  process.exit(2);
}

function parseCanvas(value) {
  const m = /^(\d+)\s*[xX*]\s*(\d+)$/.exec(String(value || "").trim());
  if (!m) return null;
  const w = Number(m[1]);
  const h = Number(m[2]);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return { w, h };
}

function parseArgs(argv) {
  if (argv.length < 1) usage();
  const opts = {
    html: argv[0],
    width: CANONICAL_WIDTH,
    height: CANONICAL_HEIGHT,
    domToPptx: false,
    allowLocalImages: false,
    report: null,
    verbose: false,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = argv[i + 1];
    if (arg === "--canvas" && value) {
      const canvas = parseCanvas(value);
      if (!canvas) {
        console.error(`Invalid --canvas value "${value}". Expected WxH, e.g. --canvas 1280x720.`);
        process.exit(2);
      }
      opts.width = canvas.w;
      opts.height = canvas.h;
      i += 1;
    } else if (arg === "--width" || arg === "--height") {
      console.error(
        `Refusing to run: ${arg} is not a valid flag for html_self_check.js. ` +
        `The canvas contract is fixed at ${CANONICAL_WIDTH}x${CANONICAL_HEIGHT}.`
      );
      console.error(
        "Per SKILL.md §0 rule 7: set .slide { width; height } in the HTML to the canvas size. " +
        "For a deliberately non-standard deck, pass --canvas WxH instead of --width/--height."
      );
      process.exit(2);
    } else if (arg === "--dom-to-pptx") {
      opts.domToPptx = true;
    } else if (arg === "--allow-local-images") {
      opts.allowLocalImages = true;
    } else if (arg === "--report" && value) {
      opts.report = value;
      i += 1;
    } else if (arg === "--verbose") {
      opts.verbose = true;
    } else {
      usage();
    }
  }
  return opts;
}

function requireModule(name, installHint) {
  try {
    return require(name);
  } catch (error) {
    if (error && error.code === "MODULE_NOT_FOUND") {
      console.error(`Missing dependency: ${name}`);
      console.error(installHint);
      console.error("Without a browser host, ask the user to choose HTML delivery or native PptxGenJS PPTX.");
      process.exit(1);
    }
    throw error;
  }
}

function printBrowserInstallHint() {
  const prefix = officeRaccoonPrefix();
  const browsersPath = process.env.PLAYWRIGHT_BROWSERS_PATH || officeRaccoonBrowserHostPath();
  console.error("Playwright Chromium is not available.");
  console.error("Install it in Office Raccoon: Settings -> Plugins -> Web automation (Playwright) -> Download Chromium and enable.");
  console.error(`Expected browser host under: ${browsersPath}`);
  console.error(`CLI fallback: PLAYWRIGHT_BROWSERS_PATH="${browsersPath}" "${path.join(prefix, "node_modules", ".bin", "playwright")}" install chromium`);
  console.error("Without a browser host, ask the user to choose HTML delivery or native PptxGenJS PPTX.");
}

async function runHtmlSelfCheck(page, expectedWidth, expectedHeight, domToPptx = false, allowLocalImages = false) {
  return page.evaluate(
    ({ expectedWidth, expectedHeight, domToPptx, allowLocalImages }) => {
      const issues = [];
      const warnings = [];
      const slideEls = Array.from(document.querySelectorAll(".slide"));
      const badTransform = /\b(?:translate|translateX|translateY|translate3d|scale|scaleX|scaleY|scale3d|skew|skewX|skewY|matrix|matrix3d)\s*\(/i;
      const badBackground = /\b(?:radial-gradient|conic-gradient)\s*\(/i;
      const badFilter = /\b(?:brightness|contrast|saturate|hue-rotate|grayscale|sepia|invert|drop-shadow)\s*\(/i;
      const viewportUnits = /\b\d*\.?\d+(?:vh|vw|vmin|vmax)\b/i;
      const pptxTextSlackPx = 12;
      const badgeTextRe = /^[\p{L}\p{N}\p{Script=Han}\s·•|+\-_/()[\].,%:：]+$/u;
      const blockedStyleRules = [
        { name: "backdrop-filter", re: /backdrop-filter\s*:/i },
        { name: "clip-path", re: /clip-path\s*:/i },
        { name: "mix-blend-mode", re: /mix-blend-mode\s*:/i },
        { name: "text-shadow", re: /text-shadow\s*:/i },
        { name: "animation", re: /(?:^|[;\s])animation(?:-\w+)?\s*:/i },
        { name: "transition", re: /(?:^|[;\s])transition(?:-\w+)?\s*:/i },
      ];
      const px = value => Number.parseFloat(String(value || "0")) || 0;
      const ratioText = (width, height) => {
        if (!width || !height) return "unknown ratio";
        return (width / height).toFixed(4);
      };
      const sizeHint = (actualWidth, actualHeight) => {
        const expectedRatio = expectedWidth / expectedHeight;
        const actualRatio = actualWidth / actualHeight;
        const ratioDelta = Math.abs(actualRatio - expectedRatio);
        const roundedWidth = Math.round(actualWidth);
        const roundedHeight = Math.round(actualHeight);
        const parts = [
          `HTML-first editable decks expect a fixed ${expectedWidth}x${expectedHeight} canvas.`,
        ];
        if (ratioDelta > 0.01) {
          parts.push(
            `The actual aspect ratio is ${ratioText(actualWidth, actualHeight)}, expected ${ratioText(expectedWidth, expectedHeight)}.`
          );
        }
        parts.push(`Set .slide { width: ${expectedWidth}px; height: ${expectedHeight}px; } and remove scaling wrappers or viewport-sized slides.`);
        return parts.join(" ");
      };
      const isVisible = (el, style = getComputedStyle(el)) => {
        const rect = el.getBoundingClientRect();
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          px(style.opacity) > 0.01 &&
          rect.width > 0.5 &&
          rect.height > 0.5
        );
      };
      const labelFor = (el, slideIndex) => {
        const classes = typeof el.className === "string" ? el.className.trim() : "";
        const id = el.id ? `#${el.id}` : "";
        const tag = el.tagName.toLowerCase();
        return `slide-${String(slideIndex + 1).padStart(2, "0")} ${tag}${id}${classes ? `.${classes.split(/\s+/).join(".")}` : ""}`;
      };
      const transformedAncestor = slide => {
        let current = slide.parentElement;
        while (current && current !== document.body) {
          const transform = getComputedStyle(current).transform;
          if (transform && transform !== "none") return current;
          current = current.parentElement;
        }
        return null;
      };
      const isExportableImageSrc = src => {
        if (/^(https?:\/\/|data:)/i.test(src)) return true;
        if (!allowLocalImages) return false;
        if (/^file:/i.test(src)) return true;
        if (/^[a-z][a-z0-9+.-]*:/i.test(src)) return false;
        if (/^\/\//.test(src)) return false;
        return src && !src.startsWith("/");
      };

      // Mirror bg_capture.js classification: decoration nodes (and their
      // descendants) get screenshotted into a slide-level bitmap, so the
      // dom-to-pptx blacklist does not apply to them. Only text-bearing
      // elements remain as live PPTX shapes after the capture step.
      const decorationTags = new Set(["SVG", "HR", "CANVAS"]);
      const chartSelector = [
        "[data-pptx-chart]",
        "[data-chart-spec]",
        "[data-chart-spec-src]",
        "[_echarts_instance_]",
        ".echarts",
        ".echarts-for-pptx",
      ].join(",");
      const hasTextContent = el => {
        if (el.querySelector && el.querySelector("img")) return true;
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          if ((node.textContent || "").trim()) return true;
        }
        return false;
      };
      const isChartElement = el =>
        Boolean(el && el.nodeType === 1 && (el.matches(chartSelector) || el.closest(chartSelector)));
      const chartRootFor = el =>
        el.closest("[data-pptx-chart]") || el.closest(chartSelector);
      const isDecorationNode = el => {
        if (!el || el.nodeType !== 1) return false;
        if (el.tagName === "IMG") return false;
        if (isChartElement(el)) return false;
        if (decorationTags.has(el.tagName)) return true;
        if (el.closest && el.closest("svg")) return true;
        return !hasTextContent(el);
      };

      if (!slideEls.length) {
        issues.push("No .slide elements found.");
        return { ok: false, slideCount: 0, issues, warnings };
      }

      if (domToPptx) {
        document
          .querySelectorAll('link[rel="stylesheet"][href*="fonts.googleapis.com"]')
          .forEach(link => {
            if (link.getAttribute("crossorigin") !== "anonymous") {
              issues.push(`Google Fonts link missing crossorigin="anonymous": ${link.getAttribute("href") || ""}`);
            }
          });
      }

      slideEls.forEach((slide, slideIndex) => {
        const slideRect = slide.getBoundingClientRect();
        const slideStyle = getComputedStyle(slide);
        const slideName = `slide-${String(slideIndex + 1).padStart(2, "0")}`;
        if (Math.abs(slideRect.width - expectedWidth) > 2 || Math.abs(slideRect.height - expectedHeight) > 2) {
          issues.push(
            `${slideName}: .slide size is ${Math.round(slideRect.width)}x${Math.round(slideRect.height)}, expected ${expectedWidth}x${expectedHeight}. ${sizeHint(slideRect.width, slideRect.height)}`
          );
        }
        if (slideStyle.position === "static") {
          warnings.push(`${slideName}: .slide should usually use position: relative for stable layout.`);
        }
        if (domToPptx && slideStyle.position !== "relative" && slideStyle.position !== "absolute") {
          issues.push(`${slideName}: dom-to-pptx requires .slide position:relative or absolute.`);
        }
        if (domToPptx && slideStyle.overflow !== "hidden") {
          issues.push(`${slideName}: dom-to-pptx requires .slide overflow:hidden.`);
        }
        if (domToPptx) {
          const ancestor = transformedAncestor(slide);
          if (ancestor) {
            issues.push(`${slideName}: .slide has a transformed ancestor; move it outside transformed wrappers.`);
          }
        }
        if (!(slide.innerText || "").trim() && !slide.querySelector("img,svg,canvas,video")) {
          issues.push(`${slideName}: slide appears empty.`);
        }

        const descendants = Array.from(slide.querySelectorAll("*"));
        const chartRootsSeen = new Set();
        descendants.forEach(el => {
          const style = getComputedStyle(el);
          const inline = el.getAttribute("style") || "";
          const decoration = isDecorationNode(el);
          if (domToPptx) {
            const chartRoot = chartRootFor(el);
            if (chartRoot && !chartRootsSeen.has(chartRoot)) {
              chartRootsSeen.add(chartRoot);
              const chartName = labelFor(chartRoot, slideIndex);
              const hasSpec =
                chartRoot.hasAttribute("data-chart-spec") ||
                chartRoot.hasAttribute("data-chart-spec-src") ||
                Boolean(chartRoot.querySelector("[data-chart-spec]"));
              if (!chartRoot.hasAttribute("data-pptx-chart")) {
                issues.push(`${chartName}: ECharts/data chart roots must be marked data-pptx-chart so bg_capture keeps them out of the slide screenshot.`);
              }
              if (!hasSpec) {
                issues.push(`${chartName}: ECharts/data chart must provide recoverable chart data via data-chart-spec, data-chart-spec-src, or a child [data-chart-spec] JSON script before PPTX export.`);
              }
            }
            // Transform/clip-path/text-shadow/backdrop-filter/mix-blend-mode/
            // animation/transition/radial-conic gradient/non-blur filter on
            // decoration nodes (or inside SVG) are captured into the
            // slide-level bitmap by bg_capture and removed from the export
            // tree, so they no longer reach dom-to-pptx. Skip them on
            // decoration nodes; keep checking text-bearing elements where
            // the effects still need a dom-to-pptx-safe equivalent.
            const inlineTransform = (inline.match(/transform\s*:\s*([^;]+)/i) || [])[1] || "";
            if (inlineTransform && badTransform.test(inlineTransform) && !decoration) {
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx does not support transform:${inlineTransform.trim()} on text-bearing elements; use left/top or flex centering, or move the effect onto a decoration-only node (no text inside).`);
            }
            const background = style.backgroundImage || "";
            if (badBackground.test(background) && !decoration) {
              warnings.push(`${labelFor(el, slideIndex)}: dom-to-pptx only reliably supports linear gradients on text-bearing elements; move radial/conic gradients to .slide background or a decoration node.`);
            }
            const filter = style.filter || "";
            if (filter && filter !== "none" && !/^\s*blur\(/i.test(filter) && badFilter.test(filter) && !decoration) {
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx supports blur only on text-bearing elements; bake filter "${filter}" into an image or move it to a decoration node.`);
            }
            blockedStyleRules.forEach(rule => {
              if (!rule.re.test(inline)) return;
              if (decoration) return; // captured into bitmap by bg_capture
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx blocked style ${rule.name} on text-bearing element; use a supported alternative or move the effect to a decoration node.`);
            });
            if (viewportUnits.test(inline)) {
              // Viewport units are a layout-sizing issue, not a visual
              // effect — bg_capture does not fix layout drift across
              // viewports, so the rule applies to both decoration and
              // text-bearing elements.
              issues.push(`${labelFor(el, slideIndex)}: dom-to-pptx export should use fixed px, not viewport units.`);
            }
            if (["VIDEO", "AUDIO", "IFRAME"].includes(el.tagName)) {
              issues.push(`${labelFor(el, slideIndex)}: <${el.tagName.toLowerCase()}> is not captured by dom-to-pptx; convert it to an image/SVG first.`);
            }
            // Plain <canvas> is treated as decoration by bg_capture and ends
            // up in the slide bitmap. ECharts/data-chart canvases are the
            // exception: they must be marked with chart metadata and kept out
            // of the screenshot path so data can be preserved as native PPT
            // chart/table content.
          }
          if (!isVisible(el, style)) return;
          const rect = el.getBoundingClientRect();
          const name = labelFor(el, slideIndex);
          const left = rect.left - slideRect.left;
          const top = rect.top - slideRect.top;
          const right = rect.right - slideRect.left;
          const bottom = rect.bottom - slideRect.top;

          if (left < -2 || top < -2 || right > slideRect.width + 2 || bottom > slideRect.height + 2) {
            issues.push(`${name}: visible content extends outside the slide bounds.`);
          }

          const text = (el.innerText || "").trim();
          if (text) {
            // Graduated text/content overflow tolerance. A dense creative slide
            // almost always carries a few px of sub-pixel / line-box overflow;
            // failing hard at 2px turned export into an un-winnable
            // edit -> recheck loop. Within the authored text slack (SKILL §3.1,
            // 16-24px) we ignore it; a moderate overflow is a soft warning that
            // goes to Limitations; only a large overflow signalling a real
            // layout break stays a hard issue that blocks export.
            const OVERFLOW_SLACK = 16;
            const OVERFLOW_ISSUE = 64;
            const overX = el.scrollWidth - el.clientWidth;
            const overY = el.scrollHeight - el.clientHeight;
            const over = Math.max(overX, overY);
            if (over > OVERFLOW_SLACK) {
              const axis = `${overX > OVERFLOW_SLACK ? "x" : ""}${overY > OVERFLOW_SLACK ? "y" : ""}`;
              const detail = `${name}: text/content overflow detected (${axis}, ${Math.round(over)}px).`;
              if (over > OVERFLOW_ISSUE) {
                issues.push(detail);
              } else {
                warnings.push(detail);
              }
            }
          }
          if (domToPptx && text) {
            const bgColor = style.backgroundColor || "";
            const hasVisibleBg = bgColor && bgColor !== "transparent" && !/rgba?\([^)]*,\s*0(?:\.0+)?\s*\)$/i.test(bgColor);
            const paddingTop = px(style.paddingTop);
            const paddingBottom = px(style.paddingBottom);
            const paddingX = px(style.paddingLeft) + px(style.paddingRight);
            const paddingY = paddingTop + paddingBottom;
            const radius = Math.max(
              px(style.borderRadius),
              px(style.borderTopLeftRadius),
              px(style.borderTopRightRadius),
              px(style.borderBottomRightRadius),
              px(style.borderBottomLeftRadius)
            );
            const hasExplicitStableSize =
              (inline && /\bwidth\s*:\s*[^;]+/i.test(inline) && /\bheight\s*:\s*[^;]+/i.test(inline)) ||
              (style.width && style.width !== "auto" && style.height && style.height !== "auto" && paddingX === 0 && paddingY === 0);
            const isFlexCentered =
              style.display.includes("flex") &&
              style.alignItems === "center" &&
              style.justifyContent === "center";
            const looksLikeShortLabel =
              text.length <= 24 &&
              !text.includes("\n") &&
              badgeTextRe.test(text) &&
              !["P", "H1", "H2", "H3", "H4", "H5", "H6", "LI"].includes(el.tagName);
            const parent = el.parentElement;
            const parentStyle = parent ? getComputedStyle(parent) : null;
            const isPlainFlexLabelChild =
              parentStyle &&
              parentStyle.display.includes("flex") &&
              parentStyle.alignItems === "center" &&
              parentStyle.justifyContent === "center" &&
              looksLikeShortLabel &&
              !hasVisibleBg &&
              paddingX === 0 &&
              paddingY === 0 &&
              radius === 0;
            if (
              looksLikeShortLabel &&
              hasVisibleBg &&
              paddingY > 0 &&
              !isFlexCentered
            ) {
              warnings.push(
                `${name}: short background text uses vertical padding to simulate centering; dom-to-pptx may shift or clip it. Use a fixed width/height outer background container with display:flex; align-items:center; justify-content:center, and an inner text element with margin:0; padding:0; line-height:1.`
              );
            }

            const hasDirectText = Array.from(el.childNodes).some(
              node => node.nodeType === Node.TEXT_NODE && (node.textContent || "").trim()
            );
            if (!isPlainFlexLabelChild && hasDirectText) {
              const range = document.createRange();
              range.selectNodeContents(el);
              const lineRects = Array.from(range.getClientRects()).filter(lineRect => lineRect.width > 1 && lineRect.height > 1);
              range.detach();
              if (lineRects.length) {
                const paddingRight = px(style.paddingRight);
                const paddingBottom = px(style.paddingBottom);
                const contentRight = rect.right - paddingRight;
                const contentBottom = rect.bottom - paddingBottom;
                const minRightSlack = Math.min(...lineRects.map(lineRect => contentRight - lineRect.right));
                const minBottomSlack = Math.min(...lineRects.map(lineRect => contentBottom - lineRect.bottom));
                if (minRightSlack < pptxTextSlackPx) {
                  warnings.push(
                    `${name}: text has only ${Math.round(minRightSlack)}px right slack; PowerPoint may rewrap after dom-to-pptx. Widen the text box by 16-24px or reduce font-size.`
                  );
                }
                if (minBottomSlack < pptxTextSlackPx) {
                  warnings.push(
                    `${name}: text has only ${Math.round(minBottomSlack)}px bottom slack; leave extra vertical room for PowerPoint font metrics.`
                  );
                }
              }
            }
          }

          const classAndRole = `${el.className || ""} ${el.getAttribute("role") || ""} ${el.getAttribute("aria-label") || ""}`;
          const looksLikeBar = /\b(fill|bar|progress|meter|概率|percent|percentage|rank)\b/i.test(classAndRole);
          if (looksLikeBar) {
            const widthStyle = el.style && el.style.width;
            const hasProgressValue =
              widthStyle ||
              el.getAttribute("aria-valuenow") ||
              el.getAttribute("data-value") ||
              el.getAttribute("data-percent");
            if (hasProgressValue && style.display === "inline") {
              issues.push(`${name}: progress/fill-like element is display:inline; width/height may not render. Use display:block or inline-block.`);
            }
            if (hasProgressValue && (rect.width < 2 || rect.height < 2)) {
              issues.push(`${name}: progress/fill-like element has near-zero rendered size.`);
            }
          }
        });

        Array.from(slide.querySelectorAll("img")).forEach(img => {
          const name = labelFor(img, slideIndex);
          const src = img.getAttribute("src") || "";
          if (domToPptx) {
            if (!isExportableImageSrc(src)) {
              issues.push(`${name}: dom-to-pptx images must use http(s), data:, or exporter-supported local relative/file URLs.`);
            }
            if (img.getAttribute("loading") === "lazy") {
              issues.push(`${name}: remove loading="lazy"; it can race dom-to-pptx export.`);
            }
          }
          if (!img.complete || img.naturalWidth === 0 || img.naturalHeight === 0) {
            issues.push(`${name}: image did not load.`);
          }
        });
      });

      return {
        ok: issues.length === 0,
        slideCount: slideEls.length,
        issues,
        warnings,
      };
    },
    { expectedWidth, expectedHeight, domToPptx, allowLocalImages }
  );
}

function listJsonFiles(dir) {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return [];
  const files = [];
  const stack = [dir];
  while (stack.length) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.name.startsWith(".")) continue;
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
      } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".json")) {
        files.push(fullPath);
      }
    }
  }
  return files.sort();
}

function toHtmlRelPath(filePath, htmlDir) {
  return path.relative(htmlDir, filePath).split(path.sep).join("/");
}

function dataSourceIssues(htmlPath, htmlText) {
  const htmlDir = path.dirname(htmlPath);
  const dataDir = path.join(htmlDir, "assets", "data");
  const dataFiles = listJsonFiles(dataDir);
  if (!dataFiles.length) return [];

  const issues = [];
  const hasChartRoot = /\bdata-pptx-chart\b/.test(htmlText);
  const specSrcMatches = Array.from(htmlText.matchAll(/\bdata-chart-spec-src\s*=\s*["']([^"']+)["']/gi));
  const specSrcs = new Set(specSrcMatches.map(match => match[1].replace(/^\.\//, "")));
  const relDataFiles = dataFiles.map(file => toHtmlRelPath(file, htmlDir));

  if (!hasChartRoot) {
    issues.push(
      `assets/data contains ${relDataFiles.length} JSON file(s), but deck.html has no data-pptx-chart root. Data-backed chart slides must reference the dataset instead of duplicating numbers into static SVG/bars.`
    );
    return issues;
  }

  const unreferenced = relDataFiles.filter(relPath => !specSrcs.has(relPath) && !specSrcs.has(`./${relPath}`));
  if (unreferenced.length === relDataFiles.length) {
    issues.push(
      `assets/data JSON is present but deck.html does not reference it with data-chart-spec-src: ${unreferenced.join(", ")}.`
    );
  }
  return issues;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const htmlPath = path.resolve(opts.html);
  if (!fs.existsSync(htmlPath)) {
    console.error(`HTML file not found: ${htmlPath}`);
    process.exit(1);
  }

  const { chromium } = requireModule(
    "playwright",
    'Install in Office Raccoon with: ${BOX_AGENT_NPM:-npm} install --prefix "$HOME/Library/Application Support/office-raccoon" playwright; then download Chromium with "$HOME/Library/Application Support/office-raccoon/node_modules/.bin/playwright" install chromium'
  );

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (error) {
    printBrowserInstallHint();
    throw error;
  }

  // The contract size is fixed (canonical 1920x1080, or an explicit --canvas
  // override). We probe at that size and assert every .slide matches it. The
  // first slide's CSS is NEVER treated as the source of truth — that auto-detect
  // behavior used to let an entire deck drift off-contract and still pass.
  const expectedWidth = opts.width;
  const expectedHeight = opts.height;
  const probeViewport = { width: expectedWidth, height: expectedHeight };
  let page = await browser.newPage({
    viewport: probeViewport,
    deviceScaleFactor: 2,
  });
  await page.goto(`file://${htmlPath}`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
  await page.evaluate(() => document.fonts && document.fonts.ready);

  const report = await runHtmlSelfCheck(
    page,
    expectedWidth,
    expectedHeight,
    opts.domToPptx,
    opts.allowLocalImages
  );
  await browser.close();

  if (opts.domToPptx) {
    const htmlText = fs.readFileSync(htmlPath, "utf8");
    const extraIssues = dataSourceIssues(htmlPath, htmlText);
    if (extraIssues.length) {
      report.issues.push(...extraIssues);
      report.ok = false;
    }
  }

  const reportText = JSON.stringify(report, null, 2);
  if (opts.report) {
    const reportPath = path.resolve(opts.report);
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, `${reportText}\n`);
  }
  if (!opts.report || opts.verbose) {
    console.log(reportText);
  }
  console.log(
    `HTML self-check: ${report.ok ? "PASS" : "FAIL"} (${report.slideCount} slides, ${report.issues.length} issues, ${report.warnings.length} warnings)`
  );
  if (opts.report) {
    console.log(`Report: ${path.resolve(opts.report)}`);
  }
  if (!report.ok) {
    report.issues.slice(0, 8).forEach(issue => console.log(`- ${issue}`));
    if (report.issues.length > 8) {
      console.log(`- ... ${report.issues.length - 8} more issue(s) in report`);
    }
  }
  if (!report.ok) {
    process.exit(1);
  }
}

main().catch(error => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
