#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { resolveArtifactPath } = require("./deck_spec_core.js");

function usage() {
  console.error(
    "Usage: finalize_controlled_deck.js deck.json --out index.html " +
    "[--manifest assets/generated/manifest.json]"
  );
  process.exit(2);
}

function parseArgs(argv) {
  if (!argv[0] || argv[0] === "--help" || argv[0] === "-h") usage();
  const opts = { deck: argv[0], out: null, manifest: null };
  for (let index = 1; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (arg === "--out" && value) {
      opts.out = value;
      index += 1;
    } else if (arg === "--manifest" && value) {
      opts.manifest = value;
      index += 1;
    } else {
      usage();
    }
  }
  if (!opts.out) usage();
  return opts;
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function writeJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function reportSummary(reportPath) {
  try {
    const report = readJson(reportPath);
    const issues = Array.isArray(report.issues)
      ? report.issues
      : Array.isArray(report.errors)
        ? report.errors
        : [];
    const warnings = Array.isArray(report.warnings)
      ? report.warnings
      : Number.isInteger(report.warnings)
        ? Array.from({ length: report.warnings }, () => "warning")
        : [];
    return { ok: report.ok === true, issues, warnings };
  } catch (_error) {
    return null;
  }
}

function tail(value, limit = 4000) {
  const text = String(value || "").trim();
  return text.length > limit ? text.slice(-limit) : text;
}

function fail(stage, result, reportPath = null) {
  const summary = reportPath ? reportSummary(reportPath) : null;
  console.error(`FINALIZE_STOP stage=${stage}`);
  if (summary && summary.issues.length) {
    console.error(JSON.stringify({ issues: summary.issues, warnings: summary.warnings }, null, 2));
  } else {
    const diagnostic = tail(`${result.stdout || ""}\n${result.stderr || ""}`);
    if (diagnostic) console.error(diagnostic);
  }
  process.exit(Number.isInteger(result.status) && result.status !== 0 ? result.status : 1);
}

function runStage(stage, scriptName, args, reportPath = null) {
  const result = spawnSync(
    process.execPath,
    [path.join(__dirname, scriptName), ...args],
    {
      cwd: process.cwd(),
      env: process.env,
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
    }
  );
  if (result.error || result.status !== 0) fail(stage, result, reportPath);
  const summary = reportPath ? reportSummary(reportPath) : null;
  if (reportPath && (!summary || !summary.ok)) fail(stage, result, reportPath);
  console.log(
    `FINALIZE_PASS stage=${stage}` +
    (summary ? ` warnings=${summary.warnings.length}` : "")
  );
}

function runAdvisoryStage(stage, scriptName, args, reportPath) {
  let previousMtime = null;
  try {
    previousMtime = fs.statSync(reportPath).mtimeMs;
  } catch (_error) {
    // The advisory may be running for the first time.
  }
  const result = spawnSync(
    process.execPath,
    [path.join(__dirname, scriptName), ...args],
    {
      cwd: process.cwd(),
      env: process.env,
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
    }
  );
  let report = null;
  let reportIsFresh = false;
  try {
    report = readJson(reportPath);
    reportIsFresh = previousMtime === null || fs.statSync(reportPath).mtimeMs !== previousMtime;
  } catch (_error) {
    report = null;
  }
  const summary = reportIsFresh ? reportSummary(reportPath) : null;
  const diagnostic = tail(
    result.error
      ? result.error.message
      : `${result.stdout || ""}\n${result.stderr || ""}`
  );
  const warnings = [
    ...(summary ? summary.warnings : []),
    ...(summary ? summary.issues : []),
  ];
  if ((result.error || result.status !== 0 || !summary) && diagnostic) {
    warnings.push(`Truth advisory could not complete cleanly: ${diagnostic}`);
  }
  const normalized = {
    ...(report && typeof report === "object" && !Array.isArray(report) ? report : {}),
    ok: true,
    advisory: true,
    issues: [],
    warnings: [...new Set(warnings)],
  };
  writeJson(reportPath, normalized);
  console.log(`FINALIZE_ADVISORY stage=${stage} warnings=${normalized.warnings.length}`);
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const deckPath = resolveArtifactPath(opts.deck);
  const outputPath = resolveArtifactPath(opts.out);
  const artifactRoot = path.dirname(deckPath);
  const manifestPath = opts.manifest
    ? resolveArtifactPath(opts.manifest)
    : path.join(artifactRoot, "assets", "generated", "manifest.json");
  const reportDir = path.join(artifactRoot, "qa");
  const reports = {
    spec: path.join(reportDir, "deck_spec.json"),
    truth: path.join(reportDir, "truth_check.json"),
    image: path.join(reportDir, "image_manifest.json"),
    html: path.join(reportDir, "html_self_check.json"),
    runtime: path.join(reportDir, "runtime_probe.json"),
  };
  fs.mkdirSync(reportDir, { recursive: true });

  runStage(
    "deck_spec",
    "validate_deck_spec.js",
    [deckPath, "--report", reports.spec],
    reports.spec
  );
  let manifestMode = "auto";
  try {
    const manifest = readJson(manifestPath);
    if (manifest && manifest.mode === "creative_image_mode") {
      manifestMode = "creative_image_mode";
    }
  } catch (_error) {
    // The manifest validator below writes the actionable missing/invalid report.
  }
  const imageArgs = [manifestPath];
  if (manifestMode === "creative_image_mode") {
    imageArgs.push("--mode", "creative_image_mode", "--min-generated", "1");
  }
  imageArgs.push("--deck", deckPath, "--report", reports.image);
  runStage("image_manifest", "validate_image_manifest.js", imageArgs, reports.image);

  runStage("render", "render_deck_html.js", [deckPath, "--out", outputPath]);
  if (!fs.existsSync(outputPath) || fs.statSync(outputPath).size === 0) {
    fail("render", { status: 1, stdout: "", stderr: `Missing output: ${outputPath}` });
  }
  runStage(
    "html_self_check",
    "html_self_check.js",
    [
      outputPath,
      "--dom-to-pptx",
      "--allow-local-images",
      "--report",
      reports.html,
    ],
    reports.html
  );
  runAdvisoryStage(
    "truth",
    "validate_deck_truth.js",
    [deckPath, "--report", reports.truth],
    reports.truth
  );
  runStage(
    "runtime_probe",
    "probe_deck_runtime.js",
    [outputPath, "--viewport", "1440x900", "--report", reports.runtime],
    reports.runtime
  );

  const warningCount = Object.values(reports)
    .map(reportSummary)
    .filter(Boolean)
    .reduce((total, report) => total + report.warnings.length, 0);
  console.log(
    JSON.stringify({
      ok: true,
      deck: deckPath,
      html: outputPath,
      qa_reports: Object.values(reports),
      warnings: warningCount,
    })
  );
}

try {
  main();
} catch (error) {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}
