#!/usr/bin/env node
"use strict";

const { buildManifest } = require("./deck_spec_core.js");

function parseArgs(argv) {
  const opts = { role: "", density: "", mediaCount: null, limit: 8, list: false };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const value = argv[index + 1];
    if (arg === "--role" && value) {
      opts.role = value.trim().toLowerCase();
      index += 1;
    } else if (arg === "--density" && value) {
      opts.density = value.trim().toLowerCase();
      index += 1;
    } else if (arg === "--media-count" && value !== undefined) {
      opts.mediaCount = Number(value);
      index += 1;
    } else if (arg === "--limit" && value) {
      opts.limit = Number(value);
      index += 1;
    } else if (arg === "--list") {
      opts.list = true;
      opts.limit = 50;
    } else if (arg === "--help" || arg === "-h") {
      console.log("Usage: query_layouts.js [--list] [--role ROLE] [--density LEVEL] [--media-count N] [--limit N]");
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!Number.isInteger(opts.limit) || opts.limit < 1 || opts.limit > 50) {
    throw new Error("--limit must be an integer from 1 to 50");
  }
  if (opts.mediaCount !== null && (!Number.isInteger(opts.mediaCount) || opts.mediaCount < 0)) {
    throw new Error("--media-count must be a non-negative integer");
  }
  return opts;
}

function scoreLayout(layout, opts) {
  let score = 0;
  if (opts.role) {
    if (!layout.roles.includes(opts.role)) return null;
    score += 100;
  }
  if (opts.density) {
    if (layout.density === opts.density) score += 20;
    else if (layout.density.includes(opts.density) || opts.density.includes(layout.density)) score += 8;
  }
  if (opts.mediaCount !== null) {
    if (opts.mediaCount < layout.mediaSlots.min || opts.mediaCount > layout.mediaSlots.max) return null;
    score += 15;
  }
  return score;
}

function compactMediaSlots(mediaSlots) {
  const slots = mediaSlots && Array.isArray(mediaSlots.slots) ? mediaSlots.slots : [];
  return {
    min: mediaSlots ? mediaSlots.min : 0,
    max: mediaSlots ? mediaSlots.max : 0,
    slots: slots.map(slot => ({
      id: slot.id,
      prop_path: slot.propPath,
      required: Boolean(slot.required),
      strategies: slot.strategies,
    })),
    background_supported: Boolean(mediaSlots && mediaSlots.background && mediaSlots.background.supported),
  };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  const results = buildManifest().layouts
    .map(layout => ({ layout, score: scoreLayout(layout, opts) }))
    .filter(item => item.score !== null)
    .sort((left, right) => right.score - left.score || left.layout.id.localeCompare(right.layout.id))
    .slice(0, opts.limit)
    .map(({ layout, score }) => ({
      id: layout.id,
      label: layout.label,
      roles: layout.roles,
      density: layout.density,
      content_shape: layout.contentShape,
      media_slots: compactMediaSlots(layout.mediaSlots),
      variants: layout.variants,
      score,
    }));
  console.log(JSON.stringify({ query: opts, count: results.length, layouts: results }));
}

try {
  main();
} catch (error) {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}
