"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { UpstreamError } = require("@spc/execution-agent-runtime");
const { createAdapter } = require("../src/reasoning-adapter");

function createCtx(post) {
  const calls = [];
  return {
    calls,
    ctx: {
      config: { reasoningTimeoutMs: 123456 },
      log: () => {},
      http: {
        signedPostEnvelope: async (...args) => {
          calls.push(args);
          return post(...args);
        },
      },
    },
  };
}

function runStub() {
  return {
    runId: "run-1",
    controller: new AbortController(),
    report: () => {},
  };
}

function validInput() {
  return {
    prompt: "分析",
    task_type: "order_delivery_analysis",
    context: { businessObjectRef: "business://order/1" },
  };
}

test("declares the read-only reasoning capability", () => {
  const { ctx } = createCtx(async () => ({ code: 0, data: {} }));
  const { capability } = createAdapter(ctx);
  assert.equal(capability.name, "reason_control_platform");
  assert.equal(capability.readOnly, true);
  assert.deepEqual(capability.constraints, { readOnly: true, requireEvidence: true });
});

test("rejects empty prompt", async () => {
  const { ctx } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);
  await assert.rejects(
    () => adapter.invoke(runStub(), { prompt: " ", task_type: "order_delivery_analysis", context: {} }),
    (e) => e.code === "INVALID_ARGUMENT",
  );
});

test("rejects missing context.businessObjectRef", async () => {
  const { ctx } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);
  const input = { ...validInput(), context: {} };
  await assert.rejects(
    () => adapter.invoke(runStub(), input),
    (e) => e.code === "INVALID_ARGUMENT" && /businessObjectRef/.test(e.message),
  );
});

test("passes config.reasoningTimeoutMs to the signed POST", async () => {
  const { ctx, calls } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);
  await adapter.invoke(runStub(), validInput());
  assert.equal(calls[0][3].timeoutMs, 123456);
});

test("returns result and lifts usage", async () => {
  const { ctx } = createCtx(async () => ({
    code: 0,
    data: { task_id: "run-1", task_type: "order_delivery_analysis", status: "succeeded", summary: "ok", usage: { total_tokens: 10 } },
  }));
  const adapter = createAdapter(ctx);
  const result = await adapter.invoke(runStub(), validInput());
  assert.deepEqual(result.result, {
    task_id: "run-1",
    task_type: "order_delivery_analysis",
    status: "succeeded",
    summary: "ok",
  });
  assert.deepEqual(result.usage, { total_tokens: 10 });
});

test("returns null on 490 cancellation", async () => {
  const { ctx } = createCtx(async () => ({ code: 490, message: "cancelled" }));
  const adapter = createAdapter(ctx);
  const result = await adapter.invoke(runStub(), validInput());
  assert.equal(result, null);
});

test("maps envelope code 504 to UPSTREAM_TIMEOUT", async () => {
  const { ctx } = createCtx(async () => ({ code: 504, message: "timeout" }));
  const adapter = createAdapter(ctx);
  await assert.rejects(
    () => adapter.invoke(runStub(), validInput()),
    (e) => e.code === "UPSTREAM_TIMEOUT",
  );
});

test("returns null when the signed POST is aborted", async () => {
  const { ctx } = createCtx(async () => {
    throw new UpstreamError("ABORTED", "请求已中止");
  });
  const adapter = createAdapter(ctx);
  const result = await adapter.invoke(runStub(), validInput());
  assert.equal(result, null);
});

test("cancel posts to cancel endpoint with a 10s timeout", async () => {
  const { ctx, calls } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);
  await adapter.cancel("run-1");
  assert.equal(calls[0][0], "/external/reasoning/tasks/run-1/cancel");
  assert.equal(calls[0][1], "reasoning.cancel");
  assert.equal(calls[0][3].timeoutMs, 10000);
});

test("prefers run.requestId and falls back to input.request_id", async () => {
  const { ctx, calls } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);

  await adapter.invoke(
    { ...runStub(), requestId: "req-run" },
    { ...validInput(), request_id: "req-input" },
  );
  assert.equal(calls[0][2].request_id, "req-run");

  calls.length = 0;
  await adapter.invoke(runStub(), { ...validInput(), request_id: "req-input" });
  assert.equal(calls[0][2].request_id, "req-input");
});
