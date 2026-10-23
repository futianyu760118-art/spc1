"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createAdapter, ALLOWED_FIELDS } = require("../src/order-adapter");

function createCtx() {
  const calls = [];
  return {
    calls,
    ctx: {
      config: { writeTimeoutMs: 9876 },
      log: () => {},
      http: {
        signedSendEnvelope: async (...args) => {
          calls.push(args);
          return { code: 0, message: "success", data: { order_no: "O-1", fields: {}, updated_at: "2026-10-20T00:00:00" } };
        },
      },
    },
  };
}

function runStub(overrides = {}) {
  return { runId: "run-7", controller: new AbortController(), report: () => {}, ...overrides };
}

test("declares the write capability with field whitelist", () => {
  const { ctx } = createCtx();
  const adapter = createAdapter(ctx);
  assert.equal(adapter.capability.name, "update_control_platform_order");
  assert.equal(adapter.capability.readOnly, false);
  assert.deepEqual(adapter.capability.constraints.allowedFields, [
    "shipping_plan",
    "delivery_completed_date",
    "customer_inspection_date",
    "planned_start_date",
  ]);
});

test("rejects missing order_no, empty fields, unknown field and bad date", async () => {
  const { ctx } = createCtx();
  const adapter = createAdapter(ctx);
  await assert.rejects(() => adapter.invoke(runStub(), { order_no: "", fields: { shipping_plan: "2026-11-01" } }), (e) => e.code === "INVALID_ARGUMENT");
  await assert.rejects(() => adapter.invoke(runStub(), { order_no: "O-1", fields: {} }), (e) => e.code === "INVALID_ARGUMENT");
  await assert.rejects(() => adapter.invoke(runStub(), { order_no: "O-1", fields: { owner: "x" } }), (e) => e.code === "INVALID_ARGUMENT");
  await assert.rejects(() => adapter.invoke(runStub(), { order_no: "O-1", fields: { shipping_plan: "2026/11/01" } }), (e) => e.code === "INVALID_ARGUMENT");
});

test("sends PUT with path, code, body, runId header and timeout; null allowed", async () => {
  const { ctx, calls } = createCtx();
  const adapter = createAdapter(ctx);
  const result = await adapter.invoke(runStub(), {
    order_no: "O-1",
    fields: { shipping_plan: "2026-11-01", delivery_completed_date: null },
    request_id: "req-1",
  });
  assert.equal(result.order_no, "O-1");
  const [method, path, code, body, opts] = calls[0];
  assert.equal(method, "PUT");
  assert.equal(path, "/external/orders/O-1/schedule");
  assert.equal(code, "orders.schedule.update");
  assert.deepEqual(body, { fields: { shipping_plan: "2026-11-01", delivery_completed_date: null }, request_id: "req-1" });
  assert.equal(opts.timeoutMs, 9876);
  assert.equal(opts.headers["X-Agent-Run-Id"], "run-7");
  assert.equal(opts.headers["X-Operator-User-Id"], undefined);
});

test("forwards operator user id header when run carries operator", async () => {
  const { ctx, calls } = createCtx();
  const adapter = createAdapter(ctx);
  await adapter.invoke(runStub({ operator: { user_id: "462" } }), {
    order_no: "O-1",
    fields: { shipping_plan: "2026-11-01" },
  });
  const [, , , , opts] = calls[0];
  assert.equal(opts.headers["X-Operator-User-Id"], "462");
  assert.equal(opts.headers["X-Agent-Run-Id"], "run-7");
});

test("maps business envelope codes to contract errors", async () => {
  const { ctx } = createCtx();
  ctx.http.signedSendEnvelope = async () => ({ code: 400, message: "订单已关闭，禁止写入" });
  const adapter = createAdapter(ctx);
  await assert.rejects(
    () => adapter.invoke(runStub(), { order_no: "O-1", fields: { shipping_plan: "2026-11-01" } }),
    (e) => e.code === "INVALID_ARGUMENT" && /已关闭/.test(e.message),
  );
});
