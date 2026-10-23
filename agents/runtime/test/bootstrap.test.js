"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { safeCancel } = require("../src/bootstrap");

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
