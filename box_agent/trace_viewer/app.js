(function () {
  "use strict";

  const model = globalThis.BoxTraceModel;
  if (!model) throw new Error("BoxTraceModel did not load");

  const state = {
    screen: "overview",
    session: null,
    records: [],
    warnings: [],
    catalog: [],
    directoryName: "",
    directoryHandle: null,
    serviceDirectoryPath: "",
    directoryRevision: "",
    directoryPoller: null,
    directoryRefreshError: "",
    catalogSkipped: [],
    selectedTurnId: "",
    selectedDetail: null,
    inspectorTrigger: null,
    detailMode: "content",
    activeView: "waterfall",
    query: "",
    filters: new Set(["llm", "tool", "error", "context"]),
    fileHandle: null,
    fileName: "",
    byteOffset: 0,
    appendTail: "",
    nextLine: 1,
    followTimer: null,
    toastTimer: null,
  };

  const LARGE_FILE_BYTES = 50 * 1024 * 1024;
  const FOLLOW_INTERVAL_MS = 1000;
  const DIRECTORY_REFRESH_INTERVAL_MS = 1000;

  const byId = (id) => document.getElementById(id);

  function appendText(parent, tagName, text, className) {
    const element = document.createElement(tagName);
    if (className) element.className = className;
    element.textContent = text == null ? "" : String(text);
    parent.appendChild(element);
    return element;
  }

  function displayTimestamp(timestamp) {
    if (!timestamp) return "—";
    const date = new Date(timestamp);
    if (Number.isNaN(date.valueOf())) return String(timestamp);
    return date.toLocaleTimeString([], { hour12: false, fractionalSecondDigits: 3 });
  }

  function displayCatalogTimestamp(timestamp) {
    if (!timestamp) return "—";
    const date = new Date(timestamp);
    if (Number.isNaN(date.valueOf())) return String(timestamp);
    return date.toLocaleString([], {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  }

  function compactId(value) {
    const text = String(value || "");
    if (text.length <= 22) return text || "—";
    return `${text.slice(0, 11)}…${text.slice(-7)}`;
  }

  function showToast(message) {
    const toast = byId("toast");
    toast.textContent = String(message || "");
    toast.hidden = false;
    if (state.toastTimer) window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
      state.toastTimer = null;
    }, 4200);
  }

  function recordCategory(record) {
    if (!record) return "context";
    if (String(record.event || "").includes("error") || (record.data && record.data.success === false)) return "error";
    if (String(record.event || "").startsWith("llm.")) return "llm";
    if (String(record.event || "").startsWith("tool.")) return "tool";
    return "context";
  }

  function recordIsVisible(record) {
    return state.filters.has(recordCategory(record)) && model.recordMatches(record, state.query);
  }

  function spanIsVisible(span) {
    const category = span.status === "error" ? "error" : span.kind;
    if (!state.filters.has(category)) return false;
    return !state.query || model.recordMatches(span.request || {}, state.query) || model.recordMatches(span.terminal || {}, state.query);
  }

  function messageIsVisible(message) {
    const category = message.role === "assistant" || message.role === "final" ? "llm" : "context";
    if (!state.filters.has(category)) return false;
    if (!state.query) return true;
    if (String(message.content || "").toLocaleLowerCase().includes(state.query.toLocaleLowerCase())) return true;
    return message.tools.some((tool) => {
      try {
        return JSON.stringify(tool).toLocaleLowerCase().includes(state.query.toLocaleLowerCase());
      } catch (_error) {
        return false;
      }
    });
  }

  function detailPayload(detail) {
    if (!detail) return { title: "Nothing selected", meta: {}, content: "Select a span, message, tool call, or event.", raw: null };
    if (detail.type === "span") {
      const span = detail.value;
      return {
        title: `${span.kind.toUpperCase()} · ${span.name}`,
        meta: { status: span.status, call_id: span.callId, step: span.step, duration: model.formatDuration(span.durationMs) },
        content: span.terminal && span.terminal.data
          ? (span.terminal.data.content || span.terminal.data.error || "No text content")
          : "This span has no terminal record.",
        raw: { request: span.request, terminal: span.terminal },
      };
    }
    if (detail.type === "message") {
      const message = detail.value;
      return {
        title: `${message.role.toUpperCase()} message`,
        meta: { role: message.sourceRole, final: message.isFinal ? "yes" : "no", tools: message.tools.length },
        content: message.content || message.thinking || "No text content",
        raw: message.raw,
      };
    }
    if (detail.type === "tool") {
      const tool = detail.value;
      return {
        title: `TOOL · ${tool.name}`,
        meta: { call_id: tool.callId, success: tool.success, duration: model.formatDuration(tool.durationMs) },
        content: tool.content || tool.error || tool.modelContent || "No result content",
        raw: {
          arguments: tool.arguments,
          content: tool.content,
          model_content: tool.modelContent,
          raw_output: tool.rawOutput,
          error: tool.error,
        },
      };
    }
    const record = detail.value;
    return {
      title: record.event || "Event",
      meta: { line: record.__line, turn: record.turn_id, step: record.step, call_id: record.llm_call_id || record.tool_call_id },
      content: record.data && (record.data.content || record.data.error || record.data.message) || "No text content",
      raw: record,
    };
  }

  function openInspector() {
    const inspector = byId("inspector");
    inspector.classList.remove("is-dismissed");
    inspector.setAttribute("aria-hidden", "false");
    byId("workspace-shell").classList.remove("is-inspector-closed");
    if (window.innerWidth <= 1160) {
      inspector.classList.add("is-open");
      byId("inspector-backdrop").hidden = false;
    }
  }

  function closeInspector(options) {
    const inspector = byId("inspector");
    const restoreFocus = !options || options.restoreFocus !== false;
    inspector.classList.remove("is-open");
    inspector.classList.add("is-dismissed");
    inspector.setAttribute("aria-hidden", "true");
    byId("workspace-shell").classList.add("is-inspector-closed");
    byId("inspector-backdrop").hidden = true;
    if (restoreFocus && state.inspectorTrigger && typeof state.inspectorTrigger.focus === "function") {
      state.inspectorTrigger.focus();
    }
  }

  function renderInspector() {
    const payload = detailPayload(state.selectedDetail);
    byId("inspector-title").textContent = payload.title;
    const meta = byId("inspector-meta");
    meta.replaceChildren();
    Object.entries(payload.meta).forEach(([key, value]) => {
      if (value == null || value === "") return;
      appendText(meta, "dt", key.replaceAll("_", " "));
      appendText(meta, "dd", value);
    });
    const content = state.detailMode === "raw"
      ? JSON.stringify(payload.raw, null, 2)
      : String(payload.content || "");
    byId("inspector-content").textContent = content;
    byId("copy-detail").disabled = !state.selectedDetail;
  }

  function selectDetail(type, value) {
    state.inspectorTrigger = document.activeElement;
    state.selectedDetail = { type, value };
    renderInspector();
    openInspector();
  }

  function currentTurn() {
    if (!state.session) return null;
    return state.session.turns.find((turn) => turn.turnId === state.selectedTurnId) || null;
  }

  function renderSummary(turn) {
    const summary = turn && turn.summary;
    byId("metric-duration").textContent = summary ? model.formatDuration(summary.durationMs) : "—";
    byId("metric-llm").textContent = summary ? `${summary.llmCalls} · ${model.formatDuration(summary.llmDurationMs)}` : "—";
    byId("metric-tools").textContent = summary ? `${summary.toolCalls} · ${model.formatDuration(summary.toolDurationMs)}` : "—";
    byId("metric-tokens").textContent = summary ? summary.totalTokens.toLocaleString() : "—";
    byId("metric-errors").textContent = summary ? String(summary.errorCount) : "—";
    byId("metric-stop").textContent = summary && summary.stopReason || "—";
  }

  function renderTurns() {
    const list = byId("turn-list");
    list.replaceChildren();
    const turns = state.session ? state.session.turns : [];
    byId("turn-count").textContent = String(turns.length);
    turns.forEach((turn, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "turn-button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(turn.turnId === state.selectedTurnId));
      appendText(button, "strong", turn.turnId || `Turn ${index + 1}`);
      appendText(button, "span", `${model.formatDuration(turn.summary.durationMs)} · ${turn.summary.totalTokens.toLocaleString()} tok`);
      button.addEventListener("click", () => selectTurn(turn.turnId));
      list.appendChild(button);
    });
  }

  function renderWaterfall(turn) {
    const rows = byId("waterfall-rows");
    const axis = byId("waterfall-axis");
    rows.replaceChildren();
    axis.replaceChildren();
    if (!turn || !turn.spans.length) return;
    const visibleSpans = turn.spans.filter(spanIsVisible);
    if (!visibleSpans.length) {
      appendText(rows, "p", "No spans match the current filters.", "panel-note");
      byId("slowest-call").textContent = "No matching calls.";
      return;
    }
    const bounds = model.timelineBounds(visibleSpans);
    const origin = bounds.originMs;
    const range = bounds.rangeMs;
    [0, 0.25, 0.5, 0.75, 1].forEach((ratio) => {
      const label = appendText(axis, "span", model.formatDuration(range * ratio));
      label.style.left = `${ratio * 100}%`;
    });
    axis.style.position = "relative";

    visibleSpans.forEach((span) => {
      const row = document.createElement("div");
      row.className = "waterfall-row";
      const label = appendText(row, "div", "", "waterfall-label");
      appendText(label, "strong", span.name);
      appendText(label, "span", compactId(span.callId));
      const track = appendText(row, "div", "", "waterfall-track");
      const bar = document.createElement("button");
      bar.type = "button";
      bar.className = "waterfall-span";
      bar.dataset.kind = span.kind;
      bar.dataset.status = span.status;
      const left = span.startMs == null ? 0 : ((span.startMs - origin) / range) * 100;
      const width = span.durationMs == null ? 1 : Math.max(1, (span.durationMs / range) * 100);
      bar.style.setProperty("--left", `${Math.max(0, left)}%`);
      bar.style.setProperty("--width", `${Math.min(100 - left, width)}%`);
      bar.textContent = model.formatDuration(span.durationMs);
      bar.title = `${span.kind} ${span.name}: ${model.formatDuration(span.durationMs)} (${span.status})`;
      bar.addEventListener("click", () => selectDetail("span", span));
      track.appendChild(bar);
      rows.appendChild(row);
    });
    const slowest = [...visibleSpans].filter((span) => span.durationMs != null).sort((a, b) => b.durationMs - a.durationMs)[0];
    byId("slowest-call").textContent = slowest
      ? `Slowest call: ${slowest.name} · ${model.formatDuration(slowest.durationMs)}`
      : "No complete spans in this turn.";
  }

  function renderTool(parent, tool) {
    if (!state.filters.has(tool.success === false ? "error" : "tool")) return;
    const branch = document.createElement("article");
    branch.className = "tool-branch";
    const button = document.createElement("button");
    button.type = "button";
    const header = appendText(button, "div", "", "message-header");
    appendText(header, "strong", `↳ TOOL · ${tool.name}`, "role-label");
    appendText(header, "span", `${model.formatDuration(tool.durationMs)} · ${tool.success === false ? "error" : tool.success === true ? "success" : "pending"}`, "message-meta");
    appendText(button, "div", tool.content || tool.error || tool.modelContent || "No terminal result", "tool-result");
    button.addEventListener("click", () => selectDetail("tool", tool));
    branch.appendChild(button);
    parent.appendChild(branch);
  }

  function renderConversation(turn) {
    const chain = byId("conversation-chain");
    chain.replaceChildren();
    if (!turn) return;
    const visibleMessages = turn.conversation.filter(messageIsVisible);
    if (!visibleMessages.length) {
      appendText(chain, "p", "No conversation nodes match the current filters.", "panel-note");
      return;
    }
    visibleMessages.forEach((message, index) => {
      const card = document.createElement("article");
      card.className = "message-card";
      card.dataset.role = message.role;
      card.dataset.final = String(message.isFinal);
      if (message.role === "system" || message.content.length > 700) card.classList.add("is-collapsed");
      const header = appendText(card, "div", "", "message-header");
      const role = message.isFinal ? "FINAL RESPONSE" : message.role.toUpperCase();
      appendText(header, "strong", role, "role-label");
      appendText(header, "span", message.record ? `line ${message.record.__line || "—"}` : `node ${index + 1}`, "message-meta");
      const content = appendText(card, "pre", message.content || "(empty response)", "message-content");
      content.tabIndex = 0;
      card.addEventListener("click", (event) => {
        if (event.target.closest(".tool-branch")) return;
        selectDetail("message", message);
      });
      if (card.classList.contains("is-collapsed")) {
        const toggle = appendText(card, "button", "Expand message", "button");
        toggle.type = "button";
        toggle.addEventListener("click", (event) => {
          event.stopPropagation();
          card.classList.toggle("is-collapsed");
          toggle.textContent = card.classList.contains("is-collapsed") ? "Expand message" : "Collapse message";
        });
      }
      message.tools.forEach((tool) => renderTool(card, tool));
      chain.appendChild(card);
    });
  }

  function renderEvents(turn) {
    const body = byId("event-table-body");
    body.replaceChildren();
    const records = turn ? turn.records.filter(recordIsVisible) : [];
    records.slice(0, 500).forEach((record) => {
      const row = document.createElement("tr");
      [
        record.__line,
        displayTimestamp(record.timestamp),
        record.event,
        record.step || "—",
        compactId(record.llm_call_id || record.tool_call_id),
      ].forEach((value) => appendText(row, "td", value));
      row.tabIndex = 0;
      row.addEventListener("click", () => selectDetail("event", record));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") selectDetail("event", record);
      });
      body.appendChild(row);
    });
    byId("event-count").textContent = records.length > 500
      ? `Showing 500 of ${records.length} events`
      : `${records.length} events`;
  }

  function renderTurn() {
    const turn = currentTurn();
    renderSummary(turn);
    renderTurns();
    renderWaterfall(turn);
    renderConversation(turn);
    renderEvents(turn);
    state.selectedDetail = null;
    renderInspector();
    closeInspector({ restoreFocus: false });
  }

  function selectTurn(turnId) {
    state.selectedTurnId = turnId;
    renderTurn();
  }

  function setView(view) {
    state.activeView = view;
    document.querySelectorAll("[data-view]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.view === view));
    });
    ["waterfall", "conversation", "events"].forEach((name) => {
      byId(`${name}-view`).hidden = name !== view;
    });
  }

  function catalogWarningText() {
    const parsingWarnings = state.catalog.reduce(
      (sum, entry) => sum + (entry.warningCount || 0),
      0,
    );
    const parts = [];
    if (state.catalogSkipped.length) {
      parts.push(`${state.catalogSkipped.length} file${state.catalogSkipped.length === 1 ? "" : "s"} skipped`);
    }
    if (parsingWarnings) {
      parts.push(`${parsingWarnings} malformed or unknown-schema line${parsingWarnings === 1 ? "" : "s"}`);
    }
    return parts.join(" · ");
  }

  function renderCatalog() {
    const totals = model.summarizeCatalog(state.catalog);
    byId("catalog-trace-count").textContent = totals.traceCount.toLocaleString();
    byId("catalog-turn-count").textContent = totals.turnCount.toLocaleString();
    byId("catalog-duration").textContent = model.formatDuration(totals.durationMs);
    byId("catalog-calls").textContent = `${totals.llmCalls.toLocaleString()} / ${totals.toolCalls.toLocaleString()}`;
    byId("catalog-tokens").textContent = totals.totalTokens.toLocaleString();
    byId("catalog-error-count").textContent = totals.errorCount.toLocaleString();
    byId("catalog-directory-name").textContent = state.directoryName
      ? `${state.directoryName} · ${totals.traceCount.toLocaleString()} trace${totals.traceCount === 1 ? "" : "s"}`
      : "Choose a directory to compare every trace at a glance.";
    byId("catalog-empty-title").textContent = state.directoryName
      ? "No usable traces in this directory"
      : "No trace directory selected";
    byId("catalog-empty-description").textContent = state.directoryName
      ? "Choose another folder, or check the warning above for files that could not be indexed."
      : "Open the folder that contains your session JSONL files. Files stay in this browser tab.";

    const body = byId("trace-catalog");
    body.replaceChildren();
    state.catalog.forEach((entry) => {
      const row = document.createElement("tr");
      row.dataset.status = entry.errorCount ? "error" : "ok";
      const identity = document.createElement("td");
      const open = appendText(identity, "button", entry.fileName, "catalog-trace-button");
      open.type = "button";
      open.addEventListener("click", () => openCatalogTrace(entry));
      appendText(identity, "small", entry.sessionId || "Session ID unavailable");
      row.appendChild(identity);
      [
        displayCatalogTimestamp(entry.startedAt || entry.lastModified),
        entry.model || "—",
        entry.turnCount.toLocaleString(),
        `${entry.llmCalls.toLocaleString()} / ${entry.toolCalls.toLocaleString()}`,
        model.formatDuration(entry.durationMs),
        entry.totalTokens.toLocaleString(),
      ].forEach((value) => appendText(row, "td", value));
      const result = document.createElement("td");
      const resultText = entry.errorCount
        ? `${entry.errorCount} error${entry.errorCount === 1 ? "" : "s"}`
        : (entry.stopReason || "incomplete");
      const badge = appendText(result, "span", resultText, "catalog-result");
      badge.dataset.status = entry.errorCount ? "error" : (entry.stopReason || "incomplete");
      row.appendChild(result);
      body.appendChild(row);
    });
    byId("catalog-empty").hidden = Boolean(state.catalog.length);
    byId("catalog-ledger").hidden = !state.catalog.length;
  }

  function showOverview() {
    stopFollowing();
    state.screen = "overview";
    byId("overview-view").hidden = false;
    byId("detail-view").hidden = true;
    byId("all-traces").hidden = true;
    byId("follow-file").disabled = true;
    const liveDirectory = Boolean(state.serviceDirectoryPath);
    byId("file-mode").textContent = liveDirectory
      ? "Directory · Live"
      : (state.directoryName ? "Directory" : "No directory loaded");
    byId("file-mode").dataset.status = liveDirectory ? "live" : (state.directoryName ? "snapshot" : "idle");
    byId("file-name").textContent = state.directoryName || "Open a trace directory";
    closeInspector({ restoreFocus: false });
    const warning = catalogWarningText();
    byId("warning-bar").hidden = !warning;
    byId("warning-bar").textContent = warning;
    renderCatalog();
    if (state.directoryPoller) state.directoryPoller.start().catch(() => undefined);
  }

  function showDetail() {
    state.screen = "detail";
    byId("overview-view").hidden = true;
    byId("detail-view").hidden = false;
    byId("all-traces").hidden = false;
    byId("follow-file").disabled = !state.fileHandle;
  }

  async function openCatalogTrace(entry) {
    await loadSnapshot(entry.file, entry.handle || null);
  }

  async function loadDirectoryFiles(entries, directoryName, directoryHandle, initialSkipped) {
    state.directoryName = directoryName || "Selected directory";
    state.directoryHandle = directoryHandle || null;
    state.catalog = [];
    state.catalogSkipped = [...(initialSkipped || [])];
    showOverview();
    byId("catalog-directory-name").textContent = `Scanning ${state.directoryName}…`;
    byId("catalog-empty").hidden = true;
    byId("catalog-ledger").hidden = true;

    const indexed = await model.indexTraceEntries(entries, LARGE_FILE_BYTES);
    state.catalog = indexed.summaries;
    state.catalogSkipped.push(...indexed.skipped);
    showOverview();
    showToast(`Indexed ${state.catalog.length.toLocaleString()} trace${state.catalog.length === 1 ? "" : "s"} from ${state.directoryName}.`);
    return state.catalog;
  }

  function openDirectoryDialog() {
    const dialog = byId("directory-dialog");
    byId("directory-path-error").hidden = true;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    window.setTimeout(() => byId("directory-path").focus(), 0);
  }

  function closeDirectoryDialog() {
    const dialog = byId("directory-dialog");
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  async function requestServiceDirectory(path, metadataOnly) {
    const response = await fetch("/api/directory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, metadataOnly: Boolean(metadataOnly) }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Local service returned HTTP ${response.status}`);
    return payload;
  }

  function serviceDirectoryEntries(payload) {
    return (payload.entries || []).map((entry) => ({
      file: new File([entry.text || ""], entry.name || "trace.jsonl", {
        type: "application/x-ndjson",
        lastModified: Number(entry.lastModified) || Date.now(),
      }),
      handle: null,
    }));
  }

  async function refreshServiceDirectory() {
    if (!state.serviceDirectoryPath || state.screen !== "overview" || document.hidden) return;
    try {
      const metadata = await requestServiceDirectory(state.serviceDirectoryPath, true);
      const revision = model.directoryEntriesRevision(metadata.entries || []);
      if (revision === state.directoryRevision) {
        state.directoryRefreshError = "";
        return;
      }
      const payload = await requestServiceDirectory(state.serviceDirectoryPath, false);
      state.directoryRevision = model.directoryEntriesRevision(payload.entries || []);
      state.directoryRefreshError = "";
      await loadDirectoryFiles(
        serviceDirectoryEntries(payload),
        payload.directory && payload.directory.path || state.serviceDirectoryPath,
        null,
        payload.skipped || [],
      );
    } catch (error) {
      const message = String(error && error.message || error);
      if (message !== state.directoryRefreshError) {
        state.directoryRefreshError = message;
        showToast(`Directory refresh failed; retrying: ${message}`);
      }
    }
  }

  function stopServiceDirectoryRefresh() {
    if (state.directoryPoller) state.directoryPoller.stop();
    state.directoryPoller = null;
    state.directoryRefreshError = "";
  }

  function startServiceDirectoryRefresh() {
    if (!state.serviceDirectoryPath) return;
    if (!state.directoryPoller) {
      state.directoryPoller = model.createDirectoryPoller({
        intervalMs: DIRECTORY_REFRESH_INTERVAL_MS,
        refresh: refreshServiceDirectory,
      });
    }
    state.directoryPoller.start().catch(() => undefined);
  }

  async function loadServiceDirectory() {
    const path = byId("directory-path").value.trim();
    const errorBox = byId("directory-path-error");
    const loadButton = byId("load-directory-path");
    errorBox.hidden = true;
    if (!path) {
      errorBox.textContent = "Enter the directory that contains your trace JSONL files.";
      errorBox.hidden = false;
      byId("directory-path").focus();
      return;
    }

    loadButton.disabled = true;
    loadButton.textContent = "Loading…";
    try {
      const payload = await requestServiceDirectory(path, false);
      const entries = serviceDirectoryEntries(payload);
      stopServiceDirectoryRefresh();
      state.serviceDirectoryPath = payload.directory && payload.directory.path || path;
      state.directoryRevision = model.directoryEntriesRevision(payload.entries || []);
      await loadDirectoryFiles(
        entries,
        state.serviceDirectoryPath,
        null,
        payload.skipped || [],
      );
      startServiceDirectoryRefresh();
      closeDirectoryDialog();
    } catch (error) {
      errorBox.textContent = `Could not load directory: ${String(error && error.message || error)}`;
      errorBox.hidden = false;
    } finally {
      loadButton.disabled = false;
      loadButton.textContent = "Load directory";
    }
  }

  async function chooseDirectory() {
    if (location.protocol === "http:" || location.protocol === "https:") {
      openDirectoryDialog();
      return;
    }
    if (typeof globalThis.showDirectoryPicker !== "function") {
      byId("directory-input").click();
      return;
    }
    try {
      const directoryHandle = await globalThis.showDirectoryPicker({ mode: "read" });
      const entries = [];
      for await (const handle of directoryHandle.values()) {
        if (handle.kind !== "file" || !handle.name.toLocaleLowerCase().endsWith(".jsonl")) continue;
        entries.push({ file: await handle.getFile(), handle });
      }
      stopServiceDirectoryRefresh();
      state.serviceDirectoryPath = "";
      state.directoryRevision = "";
      await loadDirectoryFiles(entries, directoryHandle.name, directoryHandle);
    } catch (error) {
      if (error && error.name === "AbortError") return;
      showToast(`Directory picker failed: ${String(error && error.message || error)}`);
    }
  }

  function showSession(records, warnings, fileName, mode) {
    state.records = records;
    state.session = model.buildSession(state.records);
    state.warnings = warnings || [];
    const previousTurnExists = state.session.turns.some((turn) => turn.turnId === state.selectedTurnId);
    if (!previousTurnExists) {
      state.selectedTurnId = state.session.turns[0] ? state.session.turns[0].turnId : "";
    }
    byId("file-name").textContent = fileName || state.session.sessionId || "Loaded trace";
    byId("file-mode").textContent = mode || "Snapshot";
    byId("file-mode").dataset.status = String(mode || "snapshot").toLocaleLowerCase();
    byId("empty-state").hidden = true;
    byId("trace-search").disabled = false;
    document.querySelector(".filter-group").disabled = false;
    const warningBar = byId("warning-bar");
    warningBar.hidden = !state.warnings.length;
    warningBar.textContent = state.warnings.length
      ? `${state.warnings.length} parsing warning${state.warnings.length === 1 ? "" : "s"}. Valid records remain available in Events.`
      : "";
    showDetail();
    setView(state.activeView);
    renderTurn();
  }

  function lineCountAfter(text) {
    if (!text) return 1;
    return String(text).split(/\r?\n/).length;
  }

  async function loadSnapshot(file, fileHandle) {
    if (!file) return false;
    if (file.size > LARGE_FILE_BYTES) {
      const sizeMiB = (file.size / (1024 * 1024)).toFixed(1);
      const accepted = window.confirm(
        `This trace is ${sizeMiB} MiB. Parsing it may make the page unresponsive. Continue?`,
      );
      if (!accepted) return false;
    }
    try {
      stopFollowing();
      const text = await file.text();
      const parsed = model.parseJsonl(text);
      state.fileHandle = fileHandle || null;
      state.fileName = file.name || "session trace";
      state.byteOffset = file.size;
      state.appendTail = "";
      state.nextLine = lineCountAfter(text);
      showSession(parsed.records, parsed.warnings, state.fileName, "Snapshot");
      byId("follow-file").disabled = !state.fileHandle;
      showToast(`Loaded ${parsed.records.length.toLocaleString()} records from ${state.fileName}.`);
      return true;
    } catch (error) {
      showToast(`Could not read this trace: ${String(error && error.message || error)}`);
      return false;
    }
  }

  async function chooseFile() {
    if (typeof globalThis.showOpenFilePicker !== "function") {
      byId("file-input").click();
      return;
    }
    try {
      const handles = await globalThis.showOpenFilePicker({
        multiple: false,
        types: [{
          description: "Box Agent session trace",
          accept: { "application/json": [".jsonl"] },
        }],
      });
      const handle = handles[0];
      if (handle) await loadSnapshot(await handle.getFile(), handle);
    } catch (error) {
      if (error && error.name === "AbortError") return;
      showToast(`File picker failed: ${String(error && error.message || error)}`);
    }
  }

  function ingestAppend(chunk) {
    const parsed = model.parseAppend(state.appendTail, chunk, state.nextLine);
    const indexOffset = state.records.length;
    parsed.records.forEach((record, index) => {
      record.__index = indexOffset + index;
    });
    state.records.push(...parsed.records);
    state.warnings.push(...parsed.warnings);
    state.appendTail = parsed.tail;
    state.nextLine = parsed.nextLine;
    showSession(state.records, state.warnings, state.fileName, "Live");
  }

  async function pollFileHandle() {
    if (!state.fileHandle || document.hidden) return;
    try {
      const nextFile = await state.fileHandle.getFile();
      if (nextFile.size < state.byteOffset) {
        const reload = window.confirm("The trace file was truncated or rotated. Reload it from the beginning?");
        if (reload) {
          await loadSnapshot(nextFile, state.fileHandle);
          startFollowing();
        } else {
          stopFollowing();
        }
        return;
      }
      if (nextFile.size === state.byteOffset) return;
      const chunk = await nextFile.slice(state.byteOffset).text();
      state.byteOffset = nextFile.size;
      ingestAppend(chunk);
    } catch (error) {
      stopFollowing();
      showToast(`Live follow stopped: ${String(error && error.message || error)}`);
    }
  }

  function startFollowing() {
    if (!state.fileHandle || state.followTimer) return;
    state.followTimer = window.setInterval(pollFileHandle, FOLLOW_INTERVAL_MS);
    byId("follow-file").textContent = "Follow: on";
    byId("file-mode").textContent = "Live";
    byId("file-mode").dataset.status = "live";
    pollFileHandle();
  }

  function stopFollowing() {
    if (state.followTimer) window.clearInterval(state.followTimer);
    state.followTimer = null;
    byId("follow-file").textContent = "Follow: off";
    if (state.session) {
      byId("file-mode").textContent = "Snapshot";
      byId("file-mode").dataset.status = "snapshot";
    }
  }

  function applyFilters() {
    state.query = byId("trace-search").value.trim();
    state.filters = new Set(
      [...document.querySelectorAll("[data-filter]:checked")].map((input) => input.dataset.filter),
    );
    const turn = currentTurn();
    renderWaterfall(turn);
    renderConversation(turn);
    renderEvents(turn);
  }

  async function copySelectedDetail() {
    const payload = detailPayload(state.selectedDetail);
    const text = state.detailMode === "raw"
      ? JSON.stringify(payload.raw, null, 2)
      : String(payload.content || "");
    try {
      await navigator.clipboard.writeText(text);
      showToast("Copied selected detail.");
    } catch (error) {
      showToast(`Clipboard access was denied: ${String(error && error.message || error)}`);
    }
  }

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelectorAll("[data-detail]").forEach((button) => {
    button.addEventListener("click", () => {
      state.detailMode = button.dataset.detail;
      document.querySelectorAll("[data-detail]").forEach((item) => item.setAttribute("aria-selected", String(item === button)));
      renderInspector();
    });
  });

  byId("open-file").addEventListener("click", chooseFile);
  byId("open-directory").addEventListener("click", chooseDirectory);
  byId("overview-open-directory").addEventListener("click", chooseDirectory);
  byId("cancel-directory-path").addEventListener("click", closeDirectoryDialog);
  byId("dismiss-directory-path").addEventListener("click", closeDirectoryDialog);
  byId("load-directory-path").addEventListener("click", loadServiceDirectory);
  byId("directory-path").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      loadServiceDirectory();
    }
  });
  byId("all-traces").addEventListener("click", showOverview);
  byId("empty-open-file").addEventListener("click", chooseFile);
  byId("drop-zone").addEventListener("click", chooseFile);
  byId("drop-zone").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      chooseFile();
    }
  });
  byId("file-input").addEventListener("change", async (event) => {
    const file = event.target.files && event.target.files[0];
    if (file) await loadSnapshot(file, null);
    event.target.value = "";
  });
  byId("directory-input").addEventListener("change", async (event) => {
    const files = [...(event.target.files || [])];
    const firstPath = files[0] && files[0].webkitRelativePath || "";
    const directoryName = firstPath.split("/")[0] || "Selected directory";
    const entries = files
      .filter((file) => {
        const relative = String(file.webkitRelativePath || "");
        return !relative || relative.split("/").length <= 2;
      })
      .map((file) => ({ file, handle: null }));
    if (entries.length) {
      stopServiceDirectoryRefresh();
      state.serviceDirectoryPath = "";
      state.directoryRevision = "";
      await loadDirectoryFiles(entries, directoryName, null);
    }
    event.target.value = "";
  });
  ["dragenter", "dragover"].forEach((name) => {
    byId("drop-zone").addEventListener(name, (event) => {
      event.preventDefault();
      byId("drop-zone").classList.add("is-dragging");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    byId("drop-zone").addEventListener(name, (event) => {
      event.preventDefault();
      byId("drop-zone").classList.remove("is-dragging");
    });
  });
  byId("drop-zone").addEventListener("drop", async (event) => {
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) await loadSnapshot(file, null);
  });
  byId("follow-file").addEventListener("click", () => {
    if (state.followTimer) stopFollowing();
    else startFollowing();
  });
  byId("trace-search").addEventListener("input", applyFilters);
  document.querySelectorAll("[data-filter]").forEach((input) => {
    input.addEventListener("change", applyFilters);
  });
  byId("copy-detail").addEventListener("click", copySelectedDetail);
  byId("close-inspector").addEventListener("click", () => closeInspector());
  byId("inspector-backdrop").addEventListener("click", () => closeInspector());
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("inspector").classList.contains("is-dismissed")) {
      closeInspector();
    }
  });
  window.addEventListener("resize", () => {
    const inspector = byId("inspector");
    if (inspector.classList.contains("is-dismissed")) return;
    if (window.innerWidth <= 1160 && state.selectedDetail) {
      inspector.classList.add("is-open");
      byId("inspector-backdrop").hidden = false;
    } else {
      inspector.classList.remove("is-open");
      byId("inspector-backdrop").hidden = true;
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.followTimer) pollFileHandle();
    if (!document.hidden && state.directoryPoller) state.directoryPoller.start().catch(() => undefined);
  });

  globalThis.BoxTraceViewer = {
    showSession,
    loadSnapshot,
    loadDirectoryFiles,
    refreshServiceDirectory,
    chooseDirectory,
    showOverview,
    startFollowing,
    stopFollowing,
    closeInspector,
    selectTurn,
    setView,
    state,
  };
  showOverview();
})();
