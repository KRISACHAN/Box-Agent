#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const {
  TRUTH_TEXT_MAX_CHARACTERS,
  resolveArtifactPath,
} = require("./deck_spec_core.js");

function usage() {
  console.error(
    "Usage: validate_outline.js outline.json [--min-slides N] " +
    "[--max-slides N] [--report qa/outline_check.json]"
  );
  process.exit(2);
}

function parseArgs(argv) {
  if (argv.length < 1) usage();
  const opts = {
    outlinePath: argv[0],
    minSlides: 3,
    maxSlides: 40,
    report: null,
  };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    const value = argv[i + 1];
    if (arg === "--min-slides" && value) {
      opts.minSlides = Number(value);
      i += 1;
    } else if (arg === "--max-slides" && value) {
      opts.maxSlides = Number(value);
      i += 1;
    } else if (arg === "--report" && value) {
      opts.report = value;
      i += 1;
    } else {
      usage();
    }
  }
  if (!Number.isInteger(opts.minSlides) || opts.minSlides < 1) usage();
  if (!Number.isInteger(opts.maxSlides) || opts.maxSlides < opts.minSlides) usage();
  return opts;
}

function readOutline(outlinePath) {
  const resolved = resolveArtifactPath(outlinePath);
  if (!fs.existsSync(resolved)) {
    throw new Error(`Outline file not found: ${resolved}`);
  }
  try {
    return { outline: JSON.parse(fs.readFileSync(resolved, "utf8")), resolved };
  } catch (error) {
    throw new Error(`Invalid JSON in ${resolved}: ${error.message}`);
  }
}

function text(value) {
  return typeof value === "string" ? value.trim() : "";
}

function narrativeText(value) {
  if (Array.isArray(value)) {
    return value.map(text).filter(Boolean).join("\n");
  }
  return text(value);
}

function wordLikeLength(value) {
  return Array.from(text(value)).length;
}

function normalize(value) {
  return text(value).toLowerCase().replace(/\s+/g, " ");
}

function includesAny(value, needles) {
  const normalized = normalize(value);
  return needles.some(needle => normalized.includes(needle));
}

function numberTokens(value) {
  return (String(value || "").match(/\d+(?:,\d{3})*(?:\.\d+)?%?/g) || [])
    .map(token => {
      const percent = token.endsWith("%");
      const bare = token.replace(/,/g, "").replace(/%$/, "");
      const numeric = Number(bare);
      return `${Number.isFinite(numeric) ? numeric : bare}${percent ? "%" : ""}`;
    });
}

function hasHttpUrl(value) {
  return /https?:\/\/[^\s|]+/i.test(String(value || ""));
}

function isPublicResearchOutline(outline) {
  const sourceMode = normalize(outline && outline.source_mode);
  if (!sourceMode) return false;
  if (includesAny(sourceMode, ["illustrative", "fictional", "hypothetical", "示意", "虚构"])) {
    return false;
  }
  return includesAny(sourceMode, [
    "public",
    "research",
    "authoritative",
    "公开",
    "研究",
    "权威",
  ]);
}

function hasEvidence(slide) {
  return Array.isArray(slide.evidence) && slide.evidence.some(item => text(item));
}

const ASSUMPTION_EVIDENCE_RE = /假设|示意|假定|assum(?:e|ed|ption)|illustrative|hypothetical/i;
const MISSING_PRIVATE_FACT_RE = /未提供|未给出|待补充|待确认|缺失|未知|not\s+provided|not\s+supplied|missing|unknown|tbd/i;
const PRIVATE_IDENTITY_FACT_RE = /(?:融资(?:阶段|轮次)|(?:种子|天使|成长)轮|pre[-\s]?a|series\s+[a-z]|[a-f]\s*轮|(?:公司|项目|产品)(?:名称|名为)|成立(?:年份|时间)|创始人|团队(?:成员姓名|姓名|履历|规模|人数|来源)|客户(?:名称|名单)|奖项|获奖|排名)/i;

function validate(outline, opts) {
  const issues = [];
  const warnings = [];
  const publicResearch = isPublicResearchOutline(outline);

  for (const field of ["deck_goal", "source_mode"]) {
    if (!text(outline[field])) issues.push(`Missing top-level field: ${field}`);
  }
  for (const field of ["audience", "storyline"]) {
    if (!narrativeText(outline[field])) {
      issues.push(`Missing top-level field: ${field}`);
    }
  }

  const slides = Array.isArray(outline.slides) ? outline.slides : null;
  if (!slides) {
    issues.push("Missing or invalid top-level field: slides must be an array");
    return { ok: false, issues, warnings, slideCount: 0 };
  }

  if (slides.length < opts.minSlides) {
    issues.push(`Too few slides: ${slides.length}; expected at least ${opts.minSlides}`);
  }
  if (slides.length > opts.maxSlides) {
    issues.push(`Too many slides: ${slides.length}; expected at most ${opts.maxSlides}`);
  }

  const seenTitles = new Map();
  const seenMessages = new Map();
  const evidenceUsage = new Map();
  const dataHeavyTerms = [
    "market",
    "市场",
    "tam",
    "sam",
    "som",
    "growth",
    "增长",
    "traction",
    "收入",
    "revenue",
    "financial",
    "融资",
    "成本",
    "cost",
    "roi",
    "chart",
    "图表",
    "benchmark",
    "竞品",
    "competition",
  ];
  const dataDisplayTerms = [
    "chart",
    "graph",
    "plot",
    "table",
    "dashboard",
    "scorecard",
    "kpi",
    "metric",
    "bar",
    "line",
    "area",
    "pie",
    "donut",
    "scatter",
    "waterfall",
    "funnel",
    "heatmap",
    "matrix",
    "图表",
    "表格",
    "看板",
    "仪表盘",
    "指标",
    "柱状",
    "条形",
    "折线",
    "面积",
    "饼图",
    "散点",
    "瀑布",
    "漏斗",
    "热力",
    "矩阵",
    "规模图",
    "曲线",
    "环形",
    "用途图",
  ];
  const chartWorthyTerms = [
    "market",
    "市场规模",
    "tam",
    "sam",
    "som",
    "growth",
    "增长",
    "traction",
    "financial",
    "财务",
    "cost",
    "成本",
    "roi",
    "benchmark",
    "竞品",
    "competition",
    "chart",
    "图表",
  ];

  slides.forEach((slide, index) => {
    const label = `slide-${String(index + 1).padStart(2, "0")}`;
    const expectedPage = index + 1;

    if (!slide || typeof slide !== "object" || Array.isArray(slide)) {
      issues.push(`${label}: slide must be an object`);
      return;
    }

    if (slide.page !== expectedPage) {
      issues.push(`${label}: page must be ${expectedPage}, got ${JSON.stringify(slide.page)}`);
    }

    for (const field of ["title", "message", "layout", "visual"]) {
      if (!text(slide[field])) issues.push(`${label}: missing ${field}`);
    }

    if (!Array.isArray(slide.bullets)) {
      issues.push(`${label}: bullets must be an array with 2-5 supporting points`);
    } else if (slide.bullets.length < 2) {
      warnings.push(`${label}: bullets has fewer than 2 items; add more substance`);
    } else if (slide.bullets.length > 5) {
      warnings.push(`${label}: bullets has ${slide.bullets.length} items; trim to 5 or fewer`);
    }

    if (!Array.isArray(slide.evidence)) {
      issues.push(`${label}: evidence must be an array, use [] for non-evidence slides`);
    } else {
      if (publicResearch && slide.evidence.length === 0) {
        issues.push(
          `${label}: public-authoritative research requires at least one ` +
          "claim | source | http(s) URL evidence item on every slide"
        );
      }
      slide.evidence.forEach((item, evidenceIndex) => {
        const key = normalize(item);
        if (!key) return;
        if (wordLikeLength(item) > TRUTH_TEXT_MAX_CHARACTERS) {
          issues.push(
            `${label}: evidence.${evidenceIndex} exceeds ` +
            `${TRUTH_TEXT_MAX_CHARACTERS} characters; the scaffold imports each ` +
            "evidence entry as one truth-contract fact, so split it into separate " +
            "evidence items and keep the source URL on each item"
          );
        }
        const labels = evidenceUsage.get(key) || [];
        labels.push(label);
        evidenceUsage.set(key, labels);
        if (publicResearch && !hasHttpUrl(item)) {
          issues.push(
            `${label}: evidence.${evidenceIndex} must include the actual http(s) ` +
            "source URL used for this public-research claim; do not relabel an " +
            "unbound search snippet as official/authoritative evidence"
          );
        }
        if (
          ASSUMPTION_EVIDENCE_RE.test(String(item || ""))
          && PRIVATE_IDENTITY_FACT_RE.test(String(item || ""))
          && !MISSING_PRIVATE_FACT_RE.test(String(item || ""))
        ) {
          issues.push(
            `${label}: evidence.${evidenceIndex} assumes a private identity fact ` +
            "(such as a company/project name, financing round, founding/team/client " +
            "fact, award, or ranking). Assumptions are allowed only for visibly " +
            "disclosed illustrative metrics/scenarios; use 待补充, ask once, or omit " +
            "this private fact"
          );
        }
      });
      if (publicResearch) {
        const evidenceNumbers = new Set(numberTokens(slide.evidence.join(" ")));
        const claimEntries = [
          { path: "title", value: slide.title },
          { path: "message", value: slide.message },
          ...(Array.isArray(slide.bullets)
            ? slide.bullets.map((value, bulletIndex) => ({
              path: `bullets.${bulletIndex}`,
              value,
            }))
            : []),
        ];
        claimEntries.forEach(entry => {
          numberTokens(entry.value).forEach(token => {
            if (!evidenceNumbers.has(token)) {
              issues.push(
                `${label}: ${entry.path} numeric literal ${JSON.stringify(token)} ` +
                "is not present in this page's evidence; add an exact evidence fact " +
                "or remove the unsupported/decorative number"
              );
            }
          });
        });
      }
    }

    const title = text(slide.title);
    const message = text(slide.message);
    const titleKey = normalize(title);
    const messageKey = normalize(message);

    if (wordLikeLength(title) > 42) {
      warnings.push(`${label}: title is long (${wordLikeLength(title)} chars); make it presentation-ready`);
    }
    if (wordLikeLength(message) > 120) {
      warnings.push(`${label}: message is long (${wordLikeLength(message)} chars); keep one core claim`);
    }
    if (message && message === title) {
      issues.push(`${label}: message duplicates title; use a claim, not a topic label`);
    }

    if (titleKey) {
      const firstSeen = seenTitles.get(titleKey);
      if (firstSeen) warnings.push(`${label}: title duplicates ${firstSeen}`);
      else seenTitles.set(titleKey, label);
    }
    if (messageKey) {
      const firstSeen = seenMessages.get(messageKey);
      if (firstSeen) issues.push(`${label}: message duplicates ${firstSeen}`);
      else seenMessages.set(messageKey, label);
    }

    const combined = [slide.title, slide.message, slide.layout, slide.visual, slide.notes].map(text).join(" ");
    const isDataHeavy = includesAny(combined, dataHeavyTerms);
    const isCoverLike = index === 0 || includesAny(
      `${slide.layout || ""} ${slide.visual || ""}`,
      ["cover", "封面"]
    );
    const chartWorthy = numberTokens(combined).length > 0
      || includesAny(combined, chartWorthyTerms);
    if (isDataHeavy && publicResearch && !hasEvidence(slide)) {
      warnings.push(`${label}: appears data/evidence-heavy but evidence is empty`);
    }
    if (
      isDataHeavy
      && !isCoverLike
      && chartWorthy
      && !includesAny(slide.visual, dataDisplayTerms)
    ) {
      warnings.push(`${label}: appears data-heavy but visual does not name a chart/table/KPI/dashboard data display`);
    }

    const quantitativeSummary = numberTokens(message).length >= 2
      && includesAny(slide.visual, dataDisplayTerms);
    if (
      !quantitativeSummary
      && includesAny(message, [" and ", "；", ";", "、"])
      && wordLikeLength(message) > 60
    ) {
      warnings.push(`${label}: message may contain multiple claims; consider splitting`);
    }
  });

  const storyline = narrativeText(outline.storyline);
  if (slides.length >= 6 && wordLikeLength(storyline) < 20) {
    warnings.push("storyline is very short for a multi-slide deck; make the narrative arc explicit");
  }
  evidenceUsage.forEach(labels => {
    if (labels.length > 2) {
      warnings.push(
        `evidence is reused across ${labels.length} slides (${labels.join(", ")}); ` +
        "use distinct evidence or combine repetitive pages"
      );
    }
  });

  return { ok: issues.length === 0, issues, warnings, slideCount: slides.length };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const { outline, resolved } = readOutline(opts.outlinePath);
  const result = validate(outline, opts);
  const output = { ...result, outline: resolved };
  const outputText = JSON.stringify(output, null, 2);
  if (opts.report) {
    const reportPath = resolveArtifactPath(opts.report);
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, `${outputText}\n`);
  }
  console.log(outputText);
  if (!result.ok) process.exit(1);
}

try {
  main();
} catch (error) {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}
