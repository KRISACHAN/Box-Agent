import assert from 'node:assert/strict';
import test from 'node:test';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import JSZip from 'jszip';
import { buildPptx } from '../lib/pptx_builder.mjs';

function coldCli(t, args, withPlaywright = false) {
  const root = mkdtempSync(join(tmpdir(), 'pptx-cli-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  cpSync(fileURLToPath(new URL('..', import.meta.url)), root, {
    recursive: true, filter: path => !['node_modules', 'test'].includes(basename(path)),
  });
  if (withPlaywright) {
    mkdirSync(join(root, 'node_modules'));
    symlinkSync(fileURLToPath(new URL('../node_modules/playwright', import.meta.url)), join(root, 'node_modules/playwright'), 'dir');
  }
  mkdirSync(join(root, 'bin'));
  writeFileSync(join(root, 'bin/npm'), '#!/bin/sh\necho installer-stdout\necho controlled-install-failure >&2\nexit 23\n', { mode: 0o755 });
  return spawnSync(process.execPath, [join(root, 'html_to_pptx.mjs'), ...args], {
    encoding: 'utf8', env: { ...process.env, PATH: `${join(root, 'bin')}:${process.env.PATH}` },
  });
}

test('help works before dependencies are installed', t => {
  const result = coldCli(t, ['--help']);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /--deck-dir/);
  assert.doesNotMatch(result.stderr, /setup|controlled-install-failure/);
});

for (const withPlaywright of [false, true]) {
test(`dependency failure is nonzero (Playwright preinstalled: ${withPlaywright})`, t => {
  const result = coldCli(t, ['--deck-dir', tmpdir()], withPlaywright);
  assert.notEqual(result.status, 0);
  const report = JSON.parse(result.stdout);
  assert.equal(report.status, 'failed');
  assert.equal(report.success, false);
  assert.equal(report.converted, 0);
  assert.match(result.stderr, /controlled-install-failure/);
  assert.doesNotMatch(report.detail, /final deliverable/);
});
}

for (const sourceFamily of ['Noto Sans SC', 'Xiaolai', 'Caveat']) {
test(`PPTX restores ${sourceFamily} and leaves browser IR intact`, async t => {
  const root = mkdtempSync(join(tmpdir(), 'pptx-font-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, 'assets/fonts'), { recursive: true });
  writeFileSync(join(root, 'assets/fonts/manifest.json'), JSON.stringify({ faces: [
    { delivery_family: 'Deck-test-font', source_family: sourceFamily },
  ] }));
  const generic = sourceFamily === 'Noto Sans SC' ? 'sans-serif' : 'cursive';
  const styles = { color: 'rgb(0, 0, 0)', fontSize: '32px', fontFamily: `"Deck-test-font", ${generic}` };
  const ir = { canvasWidth: 1600, canvasHeight: 900, ct: {
    tag: 'DIV', bounds: { x: 80, y: 80, w: 900, h: 150 }, styles, text: '市场 Growth 2026',
    textRuns: [
      { text: '市场 Growth ', ...styles },
      { text: '2026', ...styles, fontFamily: 'Arial', fontWeight: '700' },
    ],
  } };
  const original = JSON.stringify(ir);
  const output = join(root, 'fonts.pptx');
  const result = await buildPptx([{ path: 'slide_01.html', ir }], root, output);
  assert.equal(result.successCount, 1);
  const zip = await JSZip.loadAsync(readFileSync(output));
  const xml = await zip.file('ppt/slides/slide1.xml').async('string');
  assert.ok(xml.includes(`typeface="${sourceFamily}"`));
  assert.match(xml, /typeface="Arial"/);
  assert.doesNotMatch(xml, /Deck-test/);
  assert.equal(JSON.stringify(ir), original);
});
}
