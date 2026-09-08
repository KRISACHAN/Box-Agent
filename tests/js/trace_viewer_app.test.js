"use strict";

const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const modelPath = path.join(__dirname, "..", "..", "box_agent", "trace_viewer", "trace_model.js");
const appPath = path.join(__dirname, "..", "..", "box_agent", "trace_viewer", "app.js");

function fakeElement() {
  const listeners = new Map();
  const classes = new Set();
  return {
    hidden: false,
    disabled: false,
    value: "",
    textContent: "",
    dataset: {},
    style: { setProperty() {} },
    classList: {
      add(...names) { names.forEach((name) => classes.add(name)); },
      remove(...names) { names.forEach((name) => classes.delete(name)); },
      contains(name) { return classes.has(name); },
      toggle(name) {
        if (classes.has(name)) classes.delete(name);
        else classes.add(name);
      },
    },
    addEventListener(type, listener) { listeners.set(type, listener); },
    click() {
      this.clickCount = (this.clickCount || 0) + 1;
      const listener = listeners.get("click");
      if (listener) listener({ target: this, preventDefault() {} });
    },
    showModal() { this.showModalCount = (this.showModalCount || 0) + 1; },
    close() {},
    focus() {},
    setAttribute() {},
    removeAttribute() {},
    replaceChildren() {},
    appendChild() {},
    querySelectorAll() { return []; },
  };
}

function loadApp() {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, fakeElement());
    return elements.get(id);
  };
  globalThis.BoxTraceModel = require(modelPath);
  globalThis.location = { protocol: "file:" };
  globalThis.window = {
    innerWidth: 1400,
    setTimeout() { return 1; },
    clearTimeout() {},
    addEventListener() {},
  };
  globalThis.document = {
    hidden: false,
    getElementById: element,
    createElement() { return fakeElement(); },
    querySelector() { return fakeElement(); },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  delete require.cache[require.resolve(appPath)];
  require(appPath);
  return { viewer: globalThis.BoxTraceViewer, element };
}

test("static directory choosers preserve comparison root replacement and ledger mode", async () => {
  const { viewer, element } = loadApp();
  const directoryInput = element("directory-input");
  const dialog = element("directory-dialog");

  await viewer.chooseComparisonDirectory();
  viewer.state.comparisonDirectoryName = "first-root";
  element("comparison-open-directory").click();

  assert.equal(directoryInput.clickCount, 2, "comparison root replacement reopens the file picker");
  assert.equal(dialog.showModalCount || 0, 0, "static mode never opens the HTTP service dialog");

  await viewer.chooseDirectory();
  assert.equal(directoryInput.clickCount, 3, "opening a ledger also uses the file picker");
  assert.equal(viewer.state.directoryDialogMode, "ledger", "the next file selection is interpreted as a ledger");
});
