"use strict";

const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const assert = require("node:assert/strict");

const model = require("../../box_agent/trace_viewer/trace_model.js");

const fixtureText = fs.readFileSync(
  path.join(__dirname, "..", "fixtures", "session_trace_viewer.jsonl"),
  "utf8",
);

test("parseJsonl keeps valid records around a malformed line", () => {
  const result = model.parseJsonl(
    '{"event":"turn.input"}\nnot-json\n{"event":"turn.end"}\n',
  );

  assert.deepEqual(result.records.map((record) => record.event), [
    "turn.input",
    "turn.end",
  ]);
  assert.deepEqual(result.warnings.map((warning) => warning.line), [2]);
  assert.equal(result.records[0].__line, 1);
  assert.equal(result.records[1].__line, 3);
});

test("parseJsonl preserves unknown events and warns about unknown schema versions", () => {
  const result = model.parseJsonl(
    '{"schema_version":"future/v9","event":"provider.cache_hit","data":{"value":7}}\n',
  );

  assert.equal(result.records[0].event, "provider.cache_hit");
  assert.deepEqual(result.records[0].data, { value: 7 });
  assert.match(result.warnings[0].message, /schema/i);
});

test("buildTurn pairs LLM and tool spans and calculates literal summary values", () => {
  const parsed = model.parseJsonl(fixtureText);
  const turn = model.buildTurn(parsed.records, "turn-1");

  assert.equal(turn.spans.filter((span) => span.kind === "llm").length, 2);
  assert.equal(turn.spans.filter((span) => span.kind === "tool").length, 1);
  assert.equal(turn.spans.find((span) => span.callId === "llm-1").durationMs, 2000);
  assert.equal(turn.spans.find((span) => span.callId === "tool-1").durationMs, 1500);
  assert.deepEqual(turn.summary, {
    turnId: "turn-1",
    durationMs: 5100,
    llmCalls: 2,
    llmDurationMs: 3200,
    toolCalls: 1,
    toolDurationMs: 1500,
    totalTokens: 300,
    errorCount: 0,
    stopReason: "end_turn",
    finalContent: "done",
  });
});

test("buildTurn retains incomplete request and terminal spans", () => {
  const records = model.parseJsonl(
    [
      '{"timestamp":"2026-08-20T00:00:00Z","event":"llm.request","turn_id":"t","llm_call_id":"missing-response","data":{}}',
      '{"timestamp":"2026-08-20T00:00:01Z","event":"tool.response","turn_id":"t","tool_call_id":"missing-request","data":{"success":false,"duration_ms":40}}',
    ].join("\n"),
  ).records;

  const turn = model.buildTurn(records, "t");

  assert.deepEqual(
    turn.spans.map((span) => [span.callId, span.status]),
    [
      ["missing-response", "incomplete"],
      ["missing-request", "error"],
    ],
  );
});

test("buildTurn orders conversation roles and nests matched tool calls", () => {
  const turn = model.buildTurn(model.parseJsonl(fixtureText).records, "turn-1");
  const roles = turn.conversation.map((item) => item.role);

  assert.deepEqual(roles, ["system", "user", "assistant", "assistant"]);
  assert.equal(turn.conversation[0].content, "You are a diagnostic agent.");
  assert.equal(turn.conversation[1].content, "Research agent tracing");
  assert.equal(turn.conversation[2].tools[0].callId, "tool-1");
  assert.equal(turn.conversation[2].tools[0].content, "<img src=x onerror=alert(1)>");
  assert.equal(turn.conversation[3].content, "done");
  assert.equal(turn.conversation[3].isFinal, true);
  assert.equal(roles.filter((role) => role === "final").length, 0);
});

test("buildSession groups turns while preserving records without a turn", () => {
  const session = model.buildSession(model.parseJsonl(fixtureText).records);

  assert.equal(session.sessionId, "session-1");
  assert.equal(session.turns.length, 1);
  assert.equal(session.turns[0].turnId, "turn-1");
  assert.equal(session.sessionRecords[0].event, "session.start");
});

test("summarizeTrace creates one directory-ledger row from a session", () => {
  const parsed = model.parseJsonl(fixtureText);
  const summary = model.summarizeTrace(parsed.records, {
    name: "session_trace_viewer.jsonl",
    size: 3649,
    lastModified: Date.parse("2026-08-20T10:01:00Z"),
  });

  assert.deepEqual(summary, {
    fileName: "session_trace_viewer.jsonl",
    fileSize: 3649,
    lastModified: Date.parse("2026-08-20T10:01:00Z"),
    sessionId: "session-1",
    startedAt: "2026-08-20T10:00:00.000Z",
    model: "gpt-test",
    turnCount: 1,
    durationMs: 5100,
    llmCalls: 2,
    toolCalls: 1,
    totalTokens: 300,
    errorCount: 0,
    stopReason: "end_turn",
  });
});

test("summarizeCatalog totals rows and orders the newest trace first", () => {
  const older = {
    fileName: "older.jsonl", startedAt: "2026-08-19T10:00:00Z",
    turnCount: 2, durationMs: 1000, llmCalls: 2, toolCalls: 1,
    totalTokens: 120, errorCount: 0,
  };
  const newer = {
    fileName: "newer.jsonl", startedAt: "2026-08-20T10:00:00Z",
    turnCount: 1, durationMs: 2000, llmCalls: 1, toolCalls: 0,
    totalTokens: 80, errorCount: 1,
  };

  assert.deepEqual(model.sortTraceSummaries([older, newer]).map((item) => item.fileName), [
    "newer.jsonl",
    "older.jsonl",
  ]);
  assert.deepEqual(model.summarizeCatalog([older, newer]), {
    traceCount: 2,
    turnCount: 3,
    durationMs: 3000,
    llmCalls: 3,
    toolCalls: 1,
    totalTokens: 200,
    errorCount: 1,
  });
});

test("indexTraceEntries summarizes valid files and reports skipped files", async () => {
  const validFile = {
    name: "valid.jsonl",
    size: Buffer.byteLength(fixtureText),
    lastModified: Date.parse("2026-08-20T10:01:00Z"),
    text: async () => fixtureText,
  };
  const oversizedFile = {
    name: "large.jsonl",
    size: validFile.size + 2,
    lastModified: 0,
    text: async () => {
      throw new Error("oversized file must not be read");
    },
  };
  const brokenFile = {
    name: "broken.jsonl",
    size: 8,
    lastModified: 0,
    text: async () => "not-json",
  };

  const indexed = await model.indexTraceEntries([
    { file: validFile, handle: "valid-handle" },
    { file: oversizedFile, handle: "large-handle" },
    { file: brokenFile, handle: null },
  ], validFile.size + 1);

  assert.equal(indexed.summaries.length, 1);
  assert.equal(indexed.summaries[0].file, validFile);
  assert.equal(indexed.summaries[0].handle, "valid-handle");
  assert.equal(indexed.summaries[0].fileName, "valid.jsonl");
  assert.deepEqual(indexed.skipped, [
    { fileName: "large.jsonl", reason: "larger than 50 MiB" },
    { fileName: "broken.jsonl", reason: "no valid records" },
  ]);
});

test("directoryEntriesRevision changes only when directory metadata changes", () => {
  const first = [
    { name: "one.jsonl", size: 10, lastModified: 1000 },
    { name: "two.jsonl", size: 20, lastModified: 2000 },
  ];

  assert.equal(
    model.directoryEntriesRevision([...first].reverse()),
    model.directoryEntriesRevision(first),
  );
  assert.notEqual(
    model.directoryEntriesRevision(first),
    model.directoryEntriesRevision([...first, {
      name: "three.jsonl", size: 30, lastModified: 3000,
    }]),
  );
  assert.notEqual(
    model.directoryEntriesRevision(first),
    model.directoryEntriesRevision([
      { name: "one.jsonl", size: 11, lastModified: 1000 },
      first[1],
    ]),
  );
});

test("createDirectoryPoller refreshes immediately and on interval ticks", async () => {
  const refreshes = [];
  const scheduled = [];
  const cleared = [];
  const poller = model.createDirectoryPoller({
    intervalMs: 250,
    refresh: async () => refreshes.push(`refresh-${refreshes.length + 1}`),
    setIntervalFn(callback, delay) {
      scheduled.push({ callback, delay });
      return 73;
    },
    clearIntervalFn(timer) {
      cleared.push(timer);
    },
  });

  await poller.start();
  assert.deepEqual(refreshes, ["refresh-1"]);
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0].delay, 250);

  await scheduled[0].callback();
  assert.deepEqual(refreshes, ["refresh-1", "refresh-2"]);

  poller.stop();
  assert.deepEqual(cleared, [73]);
});

test("formatDuration produces compact diagnostic labels", () => {
  assert.equal(model.formatDuration(null), "—");
  assert.equal(model.formatDuration(420), "420 ms");
  assert.equal(model.formatDuration(2310), "2.31 s");
  assert.equal(model.formatDuration(61000), "1m 1s");
});

test("timelineBounds stays finite for incomplete spans without timestamps", () => {
  assert.deepEqual(model.timelineBounds([
    { startMs: null, endMs: null, durationMs: null },
  ]), { originMs: 0, rangeMs: 1 });

  assert.deepEqual(model.timelineBounds([
    { startMs: 100, endMs: 150, durationMs: 50 },
    { startMs: 120, endMs: null, durationMs: 100 },
  ]), { originMs: 100, rangeMs: 120 });
});

test("parseAppend retains an unfinished line until the next chunk completes it", () => {
  const first = model.parseAppend(
    "",
    '{"event":"turn.input"}\n{"event":',
    11,
  );
  assert.deepEqual(first.records.map((record) => record.event), ["turn.input"]);
  assert.equal(first.records[0].__line, 11);
  assert.equal(first.tail, '{"event":');
  assert.equal(first.nextLine, 12);

  const second = model.parseAppend(first.tail, '"turn.end"}\n', first.nextLine);
  assert.deepEqual(second.records.map((record) => record.event), ["turn.end"]);
  assert.equal(second.records[0].__line, 12);
  assert.equal(second.tail, "");
  assert.equal(second.nextLine, 13);
});

test("recordMatches finds event metadata, IDs, and nested payload text", () => {
  const record = model.parseJsonl(fixtureText).records.find(
    (item) => item.event === "tool.response",
  );

  assert.equal(model.recordMatches(record, "tool.response"), true);
  assert.equal(model.recordMatches(record, "TOOL-1"), true);
  assert.equal(model.recordMatches(record, "onerror=alert"), true);
  assert.equal(model.recordMatches(record, "not present anywhere"), false);
  assert.equal(model.recordMatches(record, "   "), true);
});
