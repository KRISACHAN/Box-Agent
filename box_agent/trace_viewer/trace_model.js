(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.BoxTraceModel = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TRACE_SCHEMA_VERSION = "box-agent-session-trace/v1";

  function parseJsonl(text) {
    const records = [];
    const warnings = [];
    String(text || "")
      .split(/\r?\n/)
      .forEach((line, index) => {
        if (!line.trim()) return;
        try {
          const value = JSON.parse(line);
          if (!value || Array.isArray(value) || typeof value !== "object") {
            throw new Error("record must be a JSON object");
          }
          const record = { ...value, __line: index + 1, __index: records.length };
          records.push(record);
          if (record.schema_version && record.schema_version !== TRACE_SCHEMA_VERSION) {
            warnings.push({
              line: index + 1,
              message: `Unknown trace schema: ${record.schema_version}`,
            });
          }
        } catch (error) {
          warnings.push({
            line: index + 1,
            message: String((error && error.message) || error),
          });
        }
      });
    return { records, warnings };
  }

  function parseAppend(tail, chunk, startLine) {
    const combined = String(tail || "") + String(chunk || "");
    const lines = combined.split(/\r?\n/);
    const endsWithNewline = /(?:\r?\n)$/.test(combined);
    const nextTail = endsWithNewline ? "" : (lines.pop() || "");
    if (endsWithNewline && lines[lines.length - 1] === "") lines.pop();
    const baseLine = Number.isInteger(startLine) && startLine > 0 ? startLine : 1;
    const parsed = parseJsonl(lines.join("\n"));
    parsed.records.forEach((record) => {
      record.__line += baseLine - 1;
    });
    parsed.warnings.forEach((warning) => {
      warning.line += baseLine - 1;
    });
    return {
      records: parsed.records,
      warnings: parsed.warnings,
      tail: nextTail,
      nextLine: baseLine + lines.length,
    };
  }

  function recordMatches(record, query) {
    const needle = String(query || "").trim().toLocaleLowerCase();
    if (!needle) return true;
    try {
      return JSON.stringify(record).toLocaleLowerCase().includes(needle);
    } catch (_error) {
      return String(record).toLocaleLowerCase().includes(needle);
    }
  }

  function timestampMs(record) {
    if (!record || !record.timestamp) return null;
    const value = Date.parse(record.timestamp);
    return Number.isFinite(value) ? value : null;
  }

  function finiteNumber(value) {
    if (value == null || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : null;
  }

  function explicitDuration(kind, terminal) {
    if (!terminal || !terminal.data) return null;
    if (kind === "llm") {
      return finiteNumber(terminal.data.timing && terminal.data.timing.duration_ms);
    }
    return finiteNumber(terminal.data.duration_ms);
  }

  function derivedDuration(request, terminal) {
    const start = timestampMs(request);
    const end = timestampMs(terminal);
    if (start == null || end == null || end < start) return null;
    return end - start;
  }

  function terminalStatus(kind, terminal) {
    if (!terminal) return "incomplete";
    if (terminal.event.endsWith(".error")) return "error";
    if (kind === "tool" && terminal.data && terminal.data.success === false) return "error";
    return "success";
  }

  function callIdFor(kind, record) {
    return kind === "llm" ? record.llm_call_id : record.tool_call_id;
  }

  function buildSpans(records) {
    const descriptors = [
      { kind: "llm", request: "llm.request", terminals: new Set(["llm.response", "llm.error"]) },
      { kind: "tool", request: "tool.request", terminals: new Set(["tool.response"]) },
    ];
    const spans = [];

    descriptors.forEach((descriptor) => {
      const requests = new Map();
      const terminals = new Map();
      records.forEach((record) => {
        const callId = callIdFor(descriptor.kind, record);
        if (!callId) return;
        if (record.event === descriptor.request && !requests.has(callId)) {
          requests.set(callId, record);
        } else if (descriptor.terminals.has(record.event) && !terminals.has(callId)) {
          terminals.set(callId, record);
        }
      });

      const ids = new Set([...requests.keys(), ...terminals.keys()]);
      ids.forEach((callId) => {
        const request = requests.get(callId) || null;
        const terminal = terminals.get(callId) || null;
        const durationMs = explicitDuration(descriptor.kind, terminal)
          ?? derivedDuration(request, terminal);
        const data = (terminal && terminal.data) || (request && request.data) || {};
        spans.push({
          kind: descriptor.kind,
          callId,
          name: descriptor.kind === "llm"
            ? (data.model || "LLM")
            : (data.tool_name || "tool"),
          request,
          terminal,
          startMs: timestampMs(request || terminal),
          endMs: timestampMs(terminal),
          durationMs,
          status: terminalStatus(descriptor.kind, terminal),
          step: (request && request.step) || (terminal && terminal.step) || null,
        });
      });
    });

    spans.sort((left, right) => {
      const leftIndex = (left.request || left.terminal || {}).__index ?? Number.MAX_SAFE_INTEGER;
      const rightIndex = (right.request || right.terminal || {}).__index ?? Number.MAX_SAFE_INTEGER;
      return leftIndex - rightIndex;
    });
    return spans;
  }

  function messageContent(message) {
    if (!message) return "";
    if (typeof message.content === "string") return message.content;
    if (message.content == null) return "";
    try {
      return JSON.stringify(message.content, null, 2);
    } catch (_error) {
      return String(message.content);
    }
  }

  function normalizeContextMessages(firstRequest) {
    const messages = (firstRequest && firstRequest.data && firstRequest.data.messages) || [];
    return messages.map((message, index) => {
      const rawRole = String(message.role || "context").toLowerCase();
      const role = rawRole === "developer" ? "system" : rawRole;
      return {
        id: `context-${index}`,
        role,
        sourceRole: rawRole,
        content: messageContent(message),
        isContext: role !== "system" && role !== "user",
        isFinal: false,
        tools: [],
        record: firstRequest,
        raw: message,
      };
    });
  }

  function toolForCall(call, toolSpans) {
    const callId = String(call && call.id || "");
    const span = toolSpans.get(callId) || null;
    const fn = (call && call.function) || {};
    const requestData = (span && span.request && span.request.data) || {};
    const terminalData = (span && span.terminal && span.terminal.data) || {};
    return {
      callId,
      name: fn.name || requestData.tool_name || terminalData.tool_name || "tool",
      arguments: fn.arguments ?? requestData.arguments ?? null,
      content: terminalData.content || "",
      modelContent: terminalData.model_content || "",
      rawOutput: terminalData.raw_output ?? null,
      error: terminalData.error || "",
      success: span ? span.status === "success" : null,
      durationMs: span ? span.durationMs : null,
      span,
    };
  }

  function buildConversation(records, spans) {
    const llmRequests = records.filter((record) => record.event === "llm.request");
    const conversation = normalizeContextMessages(llmRequests[0] || null);
    const turnInput = records.find((record) => record.event === "turn.input");
    const inputContent = turnInput && turnInput.data ? String(turnInput.data.content || "") : "";
    const hasCurrentInput = conversation.some(
      (item) => item.role === "user" && item.content === inputContent,
    );
    if (inputContent && !hasCurrentInput) {
      conversation.push({
        id: `turn-input-${turnInput.__line || 0}`,
        role: "user",
        sourceRole: "user",
        content: inputContent,
        isContext: false,
        isFinal: false,
        tools: [],
        record: turnInput,
        raw: turnInput.data,
      });
    }

    const toolSpans = new Map(
      spans.filter((span) => span.kind === "tool").map((span) => [span.callId, span]),
    );
    records
      .filter((record) => record.event === "llm.response")
      .forEach((record, index) => {
        const data = record.data || {};
        conversation.push({
          id: `assistant-${record.llm_call_id || index}`,
          role: "assistant",
          sourceRole: "assistant",
          content: String(data.content || ""),
          thinking: String(data.thinking || ""),
          isContext: false,
          isFinal: false,
          tools: (data.tool_calls || []).map((call) => toolForCall(call, toolSpans)),
          record,
          raw: data,
        });
      });

    const turnOutput = records.find((record) => record.event === "turn.output");
    const finalContent = turnOutput && turnOutput.data
      ? String(turnOutput.data.content || "")
      : "";
    if (finalContent) {
      const lastAssistant = [...conversation].reverse().find((item) => item.role === "assistant");
      if (lastAssistant && lastAssistant.content === finalContent) {
        lastAssistant.isFinal = true;
        lastAssistant.finalRecord = turnOutput;
      } else {
        conversation.push({
          id: `final-${turnOutput.__line || 0}`,
          role: "final",
          sourceRole: "assistant",
          content: finalContent,
          isContext: false,
          isFinal: true,
          tools: [],
          record: turnOutput,
          raw: turnOutput.data,
        });
      }
    }
    return conversation;
  }

  function totalTokens(records) {
    const turnEnd = [...records].reverse().find((record) => record.event === "turn.end");
    const turnUsage = turnEnd && turnEnd.data && turnEnd.data.usage;
    const explicit = finiteNumber(turnUsage && turnUsage.total_tokens);
    if (explicit != null) return explicit;
    return records
      .filter((record) => record.event === "llm.response")
      .reduce((sum, record) => sum + (finiteNumber(record.data && record.data.usage && record.data.usage.total_tokens) || 0), 0);
  }

  function buildTurn(allRecords, turnId) {
    const records = allRecords.filter((record) => String(record.turn_id || "") === String(turnId));
    const spans = buildSpans(records);
    const turnEnd = [...records].reverse().find((record) => record.event === "turn.end");
    const turnOutput = [...records].reverse().find((record) => record.event === "turn.output");
    const durationMs = finiteNumber(turnEnd && turnEnd.data && turnEnd.data.duration_ms)
      ?? derivedDuration(records[0], records[records.length - 1]);
    const errors = records.filter((record) => (
      record.event.endsWith(".error")
      || (record.event === "tool.response" && record.data && record.data.success === false)
    ));
    const llmSpans = spans.filter((span) => span.kind === "llm");
    const toolSpans = spans.filter((span) => span.kind === "tool");
    const summary = {
      turnId: String(turnId),
      durationMs,
      llmCalls: llmSpans.length,
      llmDurationMs: llmSpans.reduce((sum, span) => sum + (span.durationMs || 0), 0),
      toolCalls: toolSpans.length,
      toolDurationMs: toolSpans.reduce((sum, span) => sum + (span.durationMs || 0), 0),
      totalTokens: totalTokens(records),
      errorCount: errors.length,
      stopReason: String(
        (turnEnd && turnEnd.data && turnEnd.data.stop_reason)
        || (turnOutput && turnOutput.data && turnOutput.data.stop_reason)
        || "",
      ),
      finalContent: String(turnOutput && turnOutput.data && turnOutput.data.content || ""),
    };
    return {
      turnId: String(turnId),
      records,
      spans,
      conversation: buildConversation(records, spans),
      errors,
      summary,
    };
  }

  function buildSession(records) {
    const turnIds = [];
    const seen = new Set();
    records.forEach((record) => {
      const turnId = String(record.turn_id || "");
      if (turnId && !seen.has(turnId)) {
        seen.add(turnId);
        turnIds.push(turnId);
      }
    });
    const sessionStart = records.find((record) => record.event === "session.start");
    const firstRecord = records[0] || {};
    return {
      sessionId: String(firstRecord.session_id || ""),
      acpSessionId: String(firstRecord.acp_session_id || ""),
      metadata: (sessionStart && sessionStart.data) || {},
      sessionRecords: records.filter((record) => !record.turn_id),
      records,
      turns: turnIds.map((turnId) => buildTurn(records, turnId)),
    };
  }

  function summarizeTrace(records, file) {
    const session = buildSession(records);
    const fileInfo = file || {};
    const sessionStart = records.find((record) => record.event === "session.start") || records[0] || {};
    const modelRecord = records.find((record) => (
      (record.event === "llm.request" || record.event === "llm.response")
      && record.data
      && record.data.model
    ));
    const lastStopReason = [...session.turns]
      .reverse()
      .map((turn) => turn.summary.stopReason)
      .find(Boolean) || "";
    return {
      fileName: String(fileInfo.name || "trace.jsonl"),
      fileSize: finiteNumber(fileInfo.size) || 0,
      lastModified: finiteNumber(fileInfo.lastModified) || 0,
      sessionId: session.sessionId,
      startedAt: String(sessionStart.timestamp || ""),
      model: String(modelRecord && modelRecord.data.model || ""),
      turnCount: session.turns.length,
      durationMs: session.turns.reduce((sum, turn) => sum + (turn.summary.durationMs || 0), 0),
      llmCalls: session.turns.reduce((sum, turn) => sum + turn.summary.llmCalls, 0),
      toolCalls: session.turns.reduce((sum, turn) => sum + turn.summary.toolCalls, 0),
      totalTokens: session.turns.reduce((sum, turn) => sum + turn.summary.totalTokens, 0),
      errorCount: session.turns.reduce((sum, turn) => sum + turn.summary.errorCount, 0),
      stopReason: lastStopReason,
    };
  }

  function summaryTimestamp(summary) {
    const startedAt = Date.parse(summary.startedAt || "");
    return Number.isFinite(startedAt) ? startedAt : (finiteNumber(summary.lastModified) || 0);
  }

  function sortTraceSummaries(summaries) {
    return [...summaries].sort((left, right) => (
      summaryTimestamp(right) - summaryTimestamp(left)
      || String(left.fileName || "").localeCompare(String(right.fileName || ""))
    ));
  }

  function summarizeCatalog(summaries) {
    return summaries.reduce((totals, summary) => ({
      traceCount: totals.traceCount + 1,
      turnCount: totals.turnCount + (finiteNumber(summary.turnCount) || 0),
      durationMs: totals.durationMs + (finiteNumber(summary.durationMs) || 0),
      llmCalls: totals.llmCalls + (finiteNumber(summary.llmCalls) || 0),
      toolCalls: totals.toolCalls + (finiteNumber(summary.toolCalls) || 0),
      totalTokens: totals.totalTokens + (finiteNumber(summary.totalTokens) || 0),
      errorCount: totals.errorCount + (finiteNumber(summary.errorCount) || 0),
    }), {
      traceCount: 0,
      turnCount: 0,
      durationMs: 0,
      llmCalls: 0,
      toolCalls: 0,
      totalTokens: 0,
      errorCount: 0,
    });
  }

  async function indexTraceEntries(entries, maxFileBytes) {
    const summaries = [];
    const skipped = [];
    const limit = finiteNumber(maxFileBytes) || (50 * 1024 * 1024);
    for (const entry of entries) {
      const file = entry && entry.file;
      if (!file || !String(file.name || "").toLocaleLowerCase().endsWith(".jsonl")) continue;
      if (file.size > limit) {
        skipped.push({ fileName: file.name, reason: "larger than 50 MiB" });
        continue;
      }
      try {
        const parsed = parseJsonl(await file.text());
        if (!parsed.records.length) {
          skipped.push({ fileName: file.name, reason: "no valid records" });
          continue;
        }
        summaries.push({
          ...summarizeTrace(parsed.records, file),
          file,
          handle: entry.handle || null,
          warningCount: parsed.warnings.length,
        });
      } catch (error) {
        skipped.push({
          fileName: file.name || "unknown file",
          reason: String(error && error.message || error),
        });
      }
    }
    return { summaries: sortTraceSummaries(summaries), skipped };
  }

  function directoryEntriesRevision(entries) {
    const metadata = (Array.isArray(entries) ? entries : []).map((entry) => ({
      name: String(entry && entry.name || ""),
      size: finiteNumber(entry && entry.size) || 0,
      lastModified: finiteNumber(entry && entry.lastModified) || 0,
    }));
    metadata.sort((left, right) => left.name.localeCompare(right.name));
    return JSON.stringify(metadata);
  }

  function createDirectoryPoller(options) {
    const settings = options || {};
    if (typeof settings.refresh !== "function") {
      throw new TypeError("createDirectoryPoller requires a refresh function");
    }
    const setIntervalFn = settings.setIntervalFn || globalThis.setInterval.bind(globalThis);
    const clearIntervalFn = settings.clearIntervalFn || globalThis.clearInterval.bind(globalThis);
    const intervalMs = finiteNumber(settings.intervalMs) || 1000;
    let timer = null;
    let inFlight = null;

    function refreshNow() {
      if (inFlight) return inFlight;
      inFlight = Promise.resolve()
        .then(() => settings.refresh())
        .finally(() => {
          inFlight = null;
        });
      return inFlight;
    }

    function start() {
      if (timer == null) {
        timer = setIntervalFn(() => {
          refreshNow().catch(() => undefined);
        }, intervalMs);
      }
      return refreshNow();
    }

    function stop() {
      if (timer == null) return;
      clearIntervalFn(timer);
      timer = null;
    }

    return { start, stop, refreshNow };
  }

  function formatDuration(value) {
    const milliseconds = finiteNumber(value);
    if (milliseconds == null) return "—";
    if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
    if (milliseconds < 60000) {
      return `${(milliseconds / 1000).toFixed(2).replace(/0+$/, "").replace(/\.$/, "")} s`;
    }
    const minutes = Math.floor(milliseconds / 60000);
    const seconds = Math.floor((milliseconds % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
  }

  function timelineBounds(spans) {
    const starts = spans.map((span) => span.startMs).filter(Number.isFinite);
    const originMs = starts.length ? Math.min(...starts) : 0;
    const ends = spans.map((span) => {
      if (Number.isFinite(span.endMs)) return span.endMs;
      if (Number.isFinite(span.startMs) && Number.isFinite(span.durationMs)) {
        return span.startMs + span.durationMs;
      }
      return Number.isFinite(span.startMs) ? span.startMs : null;
    }).filter(Number.isFinite);
    const finishMs = ends.length ? Math.max(...ends, originMs + 1) : originMs + 1;
    return { originMs, rangeMs: Math.max(1, finishMs - originMs) };
  }

  return {
    TRACE_SCHEMA_VERSION,
    parseJsonl,
    parseAppend,
    recordMatches,
    buildSession,
    buildTurn,
    summarizeTrace,
    sortTraceSummaries,
    summarizeCatalog,
    indexTraceEntries,
    directoryEntriesRevision,
    createDirectoryPoller,
    formatDuration,
    timelineBounds,
  };
});
