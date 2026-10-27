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

  const result = await onLocalRun(
    "local-1",
    "query_control_platform",
    { path: "/x" },
    { user_id: "462" },
    "actor-test",
    "trace-1",
    caller,
  );

  assert.deepEqual(result, { ok: true });
  assert.equal(seenMapSize, 1);
  assert.equal(seenRun.operator.user_id, "462");
  assert.equal(seenRun.actorToken, "actor-test");
  assert.equal(seenRun.caller, caller);
  assert.equal(seenRun.traceId, "trace-1");
  assert.equal(seenRun.taskId, "AT-000123");
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

  await assert.rejects(() => onLocalRun("local-2", "query_control_platform", {}, null, "actor"), /boom/);
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

  const first = onLocalRun("local-a", "query_control_platform", {}, null, "actor");
  const second = onLocalRun("local-b", "query_control_platform", {}, null, "actor");
  await flushMicrotasks();

  assert.deepEqual(started.sort(), ["local-a", "local-b"]);
  assert.equal(connection.localRuns.size, 2);

  gates.get("local-a")();
  gates.get("local-b")();
  assert.deepEqual(await Promise.all([first, second]), ["local-a", "local-b"]);
  assert.equal(connection.localRuns.size, 0);
});
