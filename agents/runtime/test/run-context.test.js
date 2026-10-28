"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  normalizeCaller,
  normalizeRequestId,
  normalizeTargetAgentRef,
  buildRunContext,
} = require("../src/run-context");

test("normalizeCaller keeps only the five caller keys and trims values", () => {
  assert.deepEqual(
    normalizeCaller({
      systemId: " control-platform ",
      agentId: " AG-000001 ",
      userId: "",
      taskId: " AT-1 ",
      traceId: " trace-1 ",
      token: "must-not-leak",
    }),
    {
      systemId: "control-platform",
      agentId: "AG-000001",
      taskId: "AT-1",
      traceId: "trace-1",
    },
  );
  assert.equal(normalizeCaller({}), null);
  assert.equal(normalizeCaller(null), null);
});

test("normalizeRequestId prefers top-level snake_case, then camelCase, then input", () => {
  assert.equal(normalizeRequestId({ request_id: "r1" }), "r1");
  assert.equal(normalizeRequestId({ requestId: "r2" }), "r2");
  assert.equal(normalizeRequestId({ input: { request_id: "r3" } }), "r3");
  assert.equal(normalizeRequestId({ input: { requestId: "r4" } }), "r4");
  assert.equal(normalizeRequestId({ request_id: " top " }), "top");
  assert.equal(normalizeRequestId({}), null);
  assert.equal(normalizeRequestId({ request_id: "  " }), null);
});

test("normalizeTargetAgentRef accepts strings and rejects non-strings", () => {
  assert.equal(
    normalizeTargetAgentRef({ target_agent_ref: " spc-agent-order-risk " }),
    "spc-agent-order-risk",
  );
  assert.equal(normalizeTargetAgentRef({ targetAgentRef: "spc-agent-query" }), "spc-agent-query");
  assert.equal(normalizeTargetAgentRef({}), null);
  assert.throws(
    () => normalizeTargetAgentRef({ target_agent_ref: 123 }),
    (error) => error.code === "INVALID_ARGUMENT",
  );
});

test("buildRunContext creates a complete run context", () => {
  const caller = { systemId: "control-platform", agentId: "AG-000001", taskId: "AT-1", token: "x" };
  const run = buildRunContext({
    source: "hub",
    runId: "run-1",
    capability: "reason_control_platform",
    input: { task_type: "order_delivery_analysis" },
    requestId: " req-1 ",
    traceId: " trace-1 ",
    caller,
    targetAgentRef: " spc-agent-order-risk ",
  });
  assert.equal(run.source, "hub");
  assert.equal(run.requestId, "req-1");
  assert.equal(run.traceId, "trace-1");
  assert.equal(run.taskId, "AT-1");
  assert.deepEqual(run.caller, {
    systemId: "control-platform",
    agentId: "AG-000001",
    taskId: "AT-1",
  });
  assert.equal(run.targetAgentRef, "spc-agent-order-risk");
  assert.equal(run.recalled, false);
  assert.ok(run.controller instanceof AbortController);
  assert.equal(typeof run.report, "function");
});
