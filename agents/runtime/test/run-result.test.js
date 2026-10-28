"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { roundDurationMs, normalizeResult, splitOutcome } = require("../src/run-result");

test("normalizes duration_ms and run_event durationMs to integers", () => {
  assert.equal(roundDurationMs(20359.1), 20359);
  assert.equal(roundDurationMs(20359.6), 20360);
  assert.equal(roundDurationMs(null), null);
  assert.deepEqual(normalizeResult({ ok: true, duration_ms: 20359.1 }), {
    ok: true,
    duration_ms: 20359,
  });
  assert.deepEqual(normalizeResult({ ok: true }), { ok: true });
  assert.deepEqual(normalizeResult({ items: [] }), { items: [] });
});

test("splits { result, usage } outcomes and keeps raw results unchanged", () => {
  assert.deepEqual(splitOutcome({ result: { ok: true }, usage: { tokensIn: 1 } }), {
    result: { ok: true },
    usage: { tokensIn: 1 },
  });
  assert.deepEqual(splitOutcome({ ok: true }), { result: { ok: true }, usage: undefined });
  assert.deepEqual(splitOutcome({ ok: true, usage: null }), {
    result: { ok: true, usage: null },
    usage: undefined,
  });
  assert.deepEqual(splitOutcome(null), { result: null, usage: undefined });
});
