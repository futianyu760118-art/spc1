"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createLocalRunHandler, safeCancel } = require("../src/bootstrap");

function createTestLogger() {
  const entries = [];
  return {
    entries,
    log: (level, event, fields) => entries.push({ level, event, fields }),
  };
}

function flushMicrotasks() {
  return new Promise((resolve) => setImmediate(resolve));
}

test("safeCancel swallows a synchronous adapter.cancel throw and logs a warning", async () => {
  const { entries, log } = createTestLogger();
  const adapter = {
    cancel() {
      throw new Error("sync cancel failure");
    },
  };
  const onRecall = safeCancel(adapter, { agentKey: "query" }, log);

  assert.doesNotThrow(() => onRecall("run-sync"));
  await flushMicrotasks();

  assert.equal(entries.length, 1);
  assert.equal(entries[0].level, "warn");
  assert.equal(entries[0].event, "adapter_cancel_failed");
  assert.equal(entries[0].fields.agentKey, "query");
  assert.equal(entries[0].fields.runId, "run-sync");
  assert.equal(entries[0].fields.message, "sync cancel failure");
});

test("safeCancel swallows a rejected adapter.cancel promise without an unhandled rejection", async () => {
  const { entries, log } = createTestLogger();
  const adapter = {
    cancel: () => Promise.reject(new Error("async cancel failure")),
  };
  const onRecall = safeCancel(adapter, { agentKey: "query" }, log);

  assert.doesNotThrow(() => onRecall("run-async"));
  await flushMicrotasks();

  assert.equal(entries.length, 1);
  assert.equal(entries[0].level, "warn");
  assert.equal(entries[0].event, "adapter_cancel_failed");
  assert.equal(entries[0].fields.runId, "run-async");
  assert.equal(entries[0].fields.message, "async cancel failure");
});

test("safeCancel handles a null rejection reason without throwing again", async () => {
  const { entries, log } = createTestLogger();
  const adapter = {
    cancel: () => Promise.reject(null),
  };
  const onRecall = safeCancel(adapter, { agentKey: "query" }, log);

  assert.doesNotThrow(() => onRecall("run-null"));
  await flushMicrotasks();

  assert.equal(entries.length, 1);
  assert.equal(entries[0].level, "warn");
  assert.equal(entries[0].event, "adapter_cancel_failed");
  assert.equal(entries[0].fields.code, null);
  assert.equal(entries[0].fields.message, "null");
});

test("safeCancel is a no-op when the adapter has no cancel", async () => {
  const { entries, log } = createTestLogger();
  const onRecall = safeCancel({}, { agentKey: "query" }, log);

  assert.doesNotThrow(() => onRecall("run-missing"));
  await flushMicrotasks();

  assert.equal(entries.length, 0);
});

test("local run handler tracks the run in localRuns and carries caller/trace metadata", async () => {
  const { log } = createTestLogger();
  const connection = { localRuns: new Map() };
  let seenRun;
  let seenMapSize;
  const adapter = {
    invoke: async (run) => {
      seenRun = run;
      seenMapSize = connection.localRuns.size;
      return { ok: true };
    },
  };
  const onLocalRun = createLocalRunHandler(adapter, connection, log);
  const caller = { systemId: "control-platform", agentId: "AG-000001", taskId: "AT-000123" };

  const result = await onLocalRun({
    runId: "local-1",
    capability: "query_control_platform",
    input: { path: "/x" },
    operator: { user_id: "462" },
    actorToken: "actor-test",
    traceId: "trace-1",
    requestId: "req-local-1",
    targetAgentRef: null,
    caller,
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(seenMapSize, 1);
  assert.equal(seenRun.operator.user_id, "462");
  assert.equal(seenRun.actorToken, "actor-test");
  assert.deepEqual(seenRun.caller, caller);
  assert.equal(seenRun.traceId, "trace-1");
  assert.equal(seenRun.taskId, "AT-000123");
  assert.equal(seenRun.requestId, "req-local-1");
  assert.equal(seenRun.source, "local");
  assert.equal(typeof seenRun.report, "function");
  assert.ok(seenRun.controller instanceof AbortController);
  assert.equal(connection.localRuns.size, 0);
  assert.equal(connection.hubRun, undefined);
});

test("local run handler removes the run from localRuns after an adapter failure", async () => {
  const { log } = createTestLogger();
  const connection = { localRuns: new Map() };
  const adapter = {
    invoke: async () => {
      throw new Error("boom");
    },
  };
  const onLocalRun = createLocalRunHandler(adapter, connection, log);

  await assert.rejects(
    () =>
      onLocalRun({
        runId: "local-2",
        capability: "query_control_platform",
        input: {},
        actorToken: "actor",
      }),
    /boom/,
  );
  assert.equal(connection.localRuns.size, 0);
});

test("local run handler allows concurrent local runs", async () => {
  const { log } = createTestLogger();
  const connection = { localRuns: new Map() };
  const gates = new Map();
  const started = [];
  const adapter = {
    invoke: (run) => new Promise((resolve) => {
      started.push(run.runId);
      gates.set(run.runId, () => resolve(run.runId));
    }),
  };
  const onLocalRun = createLocalRunHandler(adapter, connection, log);

  const first = onLocalRun({
    runId: "local-a",
    capability: "query_control_platform",
    input: {},
    actorToken: "actor",
  });
  const second = onLocalRun({
    runId: "local-b",
    capability: "query_control_platform",
    input: {},
    actorToken: "actor",
  });
  await flushMicrotasks();

  assert.deepEqual(started.sort(), ["local-a", "local-b"]);
  assert.equal(connection.localRuns.size, 2);

  gates.get("local-a")();
  gates.get("local-b")();
  assert.deepEqual(await Promise.all([first, second]), ["local-a", "local-b"]);
  assert.equal(connection.localRuns.size, 0);
});
