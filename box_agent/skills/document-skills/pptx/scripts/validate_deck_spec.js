#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const {
  getLayout,
  readJson,
  resolveArtifactPath,
  validateAndNormalizeDeck,
} = require("./deck_spec_core.js");
const {
  analyzeOutlineLayoutIntent,
  outlineIntentRecord,
  validateOutlineVisualCardinality,
} = require("./outline_layout_contract.js");

const DESIGN_COLLECTION_FIELDS = Object.freeze({
  "statement-focus-v1": "proofs",
  "cards-grid-v1": "items",
  "quadrant-matrix-v1": "items",
  "pyramid-hierarchy-v1": "items",
  "timeline-horizontal-v1": "steps",
  "factory-process-line-v1": "stations",
  "legal-case-logic-v1": "sections",
  "property-factsheet-v1": "zones",
  "commerce-funnel-v1": "stages",
  "supply-network-v1": "nodes",
  "table-data-v1": "rows",
  "closing-next-steps-v1": "actions",
});

function designContractResolution(deck) {
  const contract = deck && deck.design_contract;
  if (!contract) return { required: false, ok: true, palette: null, slides: [] };
  const resolutions = Object.entries(contract.slides || {}).map(([slideId, requirement]) => {
    const slide = deck.slides.find(item => item.id === slideId);
    const layout = slide ? getLayout(slide.layout_id) : null;
    const collectionField = slide ? DESIGN_COLLECTION_FIELDS[slide.layout_id] : null;
    const collection = collectionField && slide.props ? slide.props[collectionField] : null;
    const kinds = layout && Array.isArray(layout.visualKinds) ? layout.visualKinds : [];
    const exact = Boolean(
      slide
      && layout
      && kinds.includes(requirement.visual_kind)
      && (!Number.isInteger(requirement.item_count)
        || (Array.isArray(collection) && collection.length === requirement.item_count))
      && (!requirement.direction
        || !Array.isArray(layout.directions)
        || !layout.directions.length
        || layout.directions.includes(requirement.direction))
      && (!requirement.relationship
        || !Array.isArray(layout.relationships)
        || !layout.relationships.length
        || layout.relationships.includes(requirement.relationship))
    );
    return {
      slide_id: slideId,
      requested: requirement,
      resolved_layout_id: slide ? slide.layout_id : null,
      resolved_item_count: Array.isArray(collection) ? collection.length : null,
      status: exact ? "exact" : "unresolved",
    };
  });
  return {
    required: true,
    ok: resolutions.every(item => item.status === "exact"),
    palette: contract.palette
      ? { requested: contract.palette, status: "exact" }
      : null,
    slides: resolutions,
  };
}

function parseArgs(argv) {
  if (!argv[0] || argv[0] === "--help" || argv[0] === "-h") {
    console.log("Usage: validate_deck_spec.js deck.json [--report report.json] [--normalized normalized.json]");
    process.exit(argv[0] ? 0 : 2);
  }
  const opts = { deck: argv[0], report: null, normalized: null };
  for (let index = 1; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (arg === "--report" && value) {
      opts.report = value;
      index += 1;
    } else if (arg === "--normalized" && value) {
      opts.normalized = value;
      index += 1;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return opts;
}

function writeJson(filePath, value) {
  const resolved = resolveArtifactPath(filePath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  fs.writeFileSync(resolved, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function normalizeBindingText(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[\s\p{P}\p{S}]+/gu, "")
    .trim();
}

function supportBindingCandidates(value) {
  const text = String(value || "").trim();
  if (!text) return [];
  const fragments = [text];
  text.split(/[。；;！？!?｜|，,、→↔•·\n]/u).forEach(fragment => {
    const trimmed = fragment.trim();
    if (!trimmed) return;
    fragments.push(trimmed);
    const labeled = trimmed.match(/^([^：:]{1,16})[：:](.+)$/u);
    if (labeled && labeled[2].trim()) {
      const label = normalizeBindingText(labeled[1]);
      // Structured layouts often place a bullet's semantic label in a node title
      // and omit the optional explanatory body.  A meaningful label is therefore
      // an exact content anchor too; short generic labels such as “结论” are not.
      if (label.length >= 4) fragments.push(labeled[1].trim());
      fragments.push(labeled[2].trim());
    }
  });
  return [...new Set(fragments.map(normalizeBindingText).filter(Boolean))];
}

function numericBindingTokens(value) {
  return [...new Set(
    (String(value || "").match(/\d+(?:,\d{3})*(?:\.\d+)?%?/g) || [])
      .map(token => token.replace(/,/g, "").replace(/%$/, ""))
      .filter(Boolean)
  )];
}

function collectText(value, output = []) {
  if (typeof value === "string") {
    output.push(value);
  } else if (Array.isArray(value)) {
    value.forEach(item => collectText(item, output));
  } else if (value && typeof value === "object") {
    Object.values(value).forEach(item => collectText(item, output));
  }
  return output;
}

function allowsIllustrativeQuantitative(deck) {
  const truthContract = deck && deck.truth_contract;
  return Boolean(
    truthContract
    && (
      truthContract.mode === "illustrative"
      || (
        Array.isArray(truthContract.assumptions)
        && truthContract.assumptions.length > 0
      )
    )
  );
}

function validateOutlineBinding(deckPath, deck) {
  const outlinePath = path.join(path.dirname(deckPath), "outline.json");
  if (!fs.existsSync(outlinePath)) {
    return { required: false, ok: true, outline: null, issues: [] };
  }
  const contractPath = path.join(path.dirname(deckPath), "qa", "deck_contract.json");
  let contract = null;
  try {
    contract = JSON.parse(fs.readFileSync(contractPath, "utf8"));
  } catch (_error) {
    // Legacy/backfilled decks may have an outline without scaffold binding.
  }
  if (!contract || !contract.outline_binding) {
    return {
      required: false,
      ok: true,
      outline: outlinePath,
      legacy_unbound: true,
      issues: [],
    };
  }
  let outline;
  try {
    outline = JSON.parse(fs.readFileSync(outlinePath, "utf8"));
  } catch (error) {
    return {
      required: true,
      ok: false,
      outline: outlinePath,
      issues: [`outline.json: invalid JSON (${error.message})`],
    };
  }
  const outlineSlides = Array.isArray(outline.slides) ? outline.slides : null;
  if (!outlineSlides) {
    return {
      required: true,
      ok: false,
      outline: outlinePath,
      issues: ["outline.json: slides must be an array"],
    };
  }
  const issues = [];
  const deckSlides = deck && Array.isArray(deck.slides) ? deck.slides : [];
  const layoutPolicy = {
    allowIllustrativeQuantitative: allowsIllustrativeQuantitative(deck),
  };
  const requiresPersistedIntent = Number(contract.contract_version || 1) >= 2;
  if (deckSlides.length !== outlineSlides.length) {
    issues.push(
      `slides: deck has ${deckSlides.length} page(s), but outline.json has ` +
      `${outlineSlides.length}`
    );
  }
  deckSlides.forEach((slide, index) => {
    const outlineSlide = outlineSlides[index];
    const slideId = slide && typeof slide.id === "string" ? slide.id : String(index);
    const basePath = `slides.${slideId}`;
    if (!outlineSlide || typeof outlineSlide !== "object") {
      issues.push(`${basePath}: no matching outline page ${index + 1}`);
      return;
    }
    const expectedPage = index + 1;
    if (slide.source_outline_page !== expectedPage) {
      issues.push(
        `${basePath}.source_outline_page: expected ${expectedPage}, got ` +
        `${JSON.stringify(slide.source_outline_page)}`
      );
    }
    const expectedIntent = outlineIntentRecord(outlineSlide);
    const actualIntent = slide && slide.outline_intent;
    if (requiresPersistedIntent && (!actualIntent || typeof actualIntent !== "object")) {
      issues.push(
        `${basePath}.outline_intent: required by deck contract v2; preserve the bound ` +
        "outline title, message, layout, and visual intent"
      );
    } else if (actualIntent && typeof actualIntent === "object") {
      Object.entries(expectedIntent).forEach(([field, expected]) => {
        const actual = typeof actualIntent[field] === "string"
          ? actualIntent[field].trim()
          : actualIntent[field];
        if (actual === expected) return;
        issues.push(
          `${basePath}.outline_intent.${field}: expected bound outline value ` +
          `${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
        );
      });
    }
    const semantic = analyzeOutlineLayoutIntent(
      outlineSlide,
      outline.source_mode,
      layoutPolicy
    );
    if (semantic && !semantic.allowed_layout_ids.includes(slide.layout_id)) {
      issues.push(
        `${basePath}.layout_id: ${JSON.stringify(slide.layout_id)} does not express ` +
        `outline visual intent ${JSON.stringify(outlineSlide.visual)}; use one of ` +
        semantic.allowed_layout_ids.join(", ")
      );
    }
    issues.push(...validateOutlineVisualCardinality(slide, outlineSlide, basePath));
    const rawPropText = collectText(slide.props).join(" ");
    const propText = normalizeBindingText(rawPropText);
    const expectedTitle = normalizeBindingText(outlineSlide.title);
    if (expectedTitle && !propText.includes(expectedTitle)) {
      issues.push(
        `${basePath}.props: must include outline page ${expectedPage} title ` +
        `${JSON.stringify(outlineSlide.title)}`
      );
    }
    const supportCandidates = [
      outlineSlide.message,
      ...(Array.isArray(outlineSlide.bullets) ? outlineSlide.bullets : []),
    ].flatMap(supportBindingCandidates);
    const supportNumericTokens = numericBindingTokens([
      outlineSlide.message,
      ...(Array.isArray(outlineSlide.bullets) ? outlineSlide.bullets : []),
    ].join(" "));
    const propNumericTokens = new Set(numericBindingTokens(rawPropText));
    const quantitativeSupportPreserved = supportNumericTokens.length > 0
      && supportNumericTokens.every(token => propNumericTokens.has(token));
    if (
      supportCandidates.length
      && !supportCandidates.some(candidate => propText.includes(candidate))
      && !quantitativeSupportPreserved
    ) {
      issues.push(
        `${basePath}.props: must preserve at least one exact message/bullet fragment from ` +
        `outline page ${expectedPage}; do not replace the page topic`
      );
    }
  });
  return {
    required: true,
    ok: issues.length === 0,
    outline: outlinePath,
    source_mode: typeof outline.source_mode === "string" ? outline.source_mode : null,
    page_count: outlineSlides.length,
    issues,
  };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const deckPath = resolveArtifactPath(opts.deck);
  const result = validateAndNormalizeDeck(readJson(opts.deck));
  const structuralIssues = [...result.issues];
  const outlineBinding = validateOutlineBinding(deckPath, result.normalized);
  result.issues.push(...outlineBinding.issues);
  const designContract = designContractResolution(result.normalized);
  const report = {
    ok: result.ok && outlineBinding.ok && designContract.ok,
    deck: deckPath,
    slideCount: result.normalized ? result.normalized.slides.length : 0,
    issues: result.issues,
    structuralIssues,
    warnings: result.warnings,
    outlineBinding,
    designContract,
  };
  if (opts.report) writeJson(opts.report, report);
  if (opts.normalized && report.ok) writeJson(opts.normalized, result.normalized);
  console.log(JSON.stringify(report, null, 2));
  console.log(
    `Deck spec validation: ${report.ok ? "PASS" : "FAIL"} ` +
    `(${report.slideCount} slides, ${report.issues.length} issues)`
  );
  if (!report.ok) process.exit(1);
}

if (require.main === module) {
  try {
    main();
  } catch (error) {
    console.error(error && error.stack ? error.stack : String(error));
    process.exit(1);
  }
}

module.exports = { validateOutlineBinding };
