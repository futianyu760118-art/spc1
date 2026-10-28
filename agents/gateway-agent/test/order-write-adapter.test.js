"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createAdapter, mapWriteError } = require("../src/order-write-adapter");

function createCtx(post) {
  const calls = [];
  return {
    calls,
    ctx: {
      config: { writeTimeoutMs: 12345 },
      log: () => {},
      http: {
        signedSendEnvelope: async (...args) => {
          calls.push(args);
          return post(...args);
        },
      },
    },
  };
}

function runStub(overrides = {}) {
  return {
    runId: "run-write-1",
    requestId: "req-write-1",
    controller: new AbortController(),
    report: () => {},
    caller: { systemId: "aeos-hub", userId: "m01:user:1" },
    ...overrides,
  };
}

function noteInput(overrides = {}) {
  return {
    operation: "order.update_note",
    orderNo: " HJY-1 ",
    changes: { remark: "new note" },
    idempotencyKey: "idem-1",
    ...overrides,
  };
}

test("declares a writable idempotent capability", () => {
  const { ctx } = createCtx(async () => ({ code: 0, data: {} }));
  const { capability } = createAdapter(ctx);
  assert.equal(capability.name, "write_control_platform");
  assert.equal(capability.readOnly, false);
  assert.equal(capability.constraints.readOnly, false);
  assert.equal(capability.constraints.idempotent, true);
  assert.deepEqual(
    capability.operations.map((operation) => operation.name),
    [
      "order.update_note",
      "order.update_status",
      "order.update_delivery_date",
    ],
  );
  const delivery = capability.operations.find(
    (operation) => operation.name === "order.update_delivery_date",
  );
  assert.deepEqual(delivery.fields, [
    { name: "deliveryDate", label: "交付日期", type: "date", required: true },
  ]);
  assert.deepEqual(capability.inputSchema.properties.changes.properties.status.enum, [
    "open",
    "closed",
  ]);
});

test("sends a normalized write request and falls back to run.requestId", async () => {
  const { ctx, calls } = createCtx(async () => ({
    code: 0,
    data: { ok: true, idempotent_replay: false },
  }));
  const adapter = createAdapter(ctx);
  const result = await adapter.invoke(runStub(), noteInput({ idempotencyKey: "" }));
  assert.equal(result.ok, true);
  assert.equal(calls[0][0], "PUT");
  assert.equal(calls[0][1], "/external/orders/HJY-1/write");
  assert.equal(calls[0][2], "orders.write");
  assert.equal(calls[0][3].operation, "order.update_note");
  assert.equal(calls[0][3].changes.remark, "new note");
  assert.equal(calls[0][3].idempotencyKey, "req-write-1");
  assert.equal(calls[0][3].request_id, "req-write-1");
  assert.equal(calls[0][4].timeoutMs, 12345);
  assert.equal(calls[0][4].headers["X-Hub-Caller-User-Id"], "m01:user:1");
});

test("sends delivery date requests", async () => {
  const { ctx, calls } = createCtx(async () => ({
    code: 0,
    data: { ok: true, idempotent_replay: false },
  }));
  const adapter = createAdapter(ctx);
  await adapter.invoke(runStub(), {
    operation: "order.update_delivery_date",
    orderNo: "HJY-1",
    changes: { deliveryDate: "2026-11-10" },
    idempotencyKey: "idem-delivery",
  });
  assert.equal(calls[0][3].operation, "order.update_delivery_date");
  assert.equal(calls[0][3].changes.deliveryDate, "2026-11-10");
});

test("validates operation, changes and idempotency key", async () => {
  const { ctx } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);
  await assert.rejects(
    () => adapter.invoke(runStub(), noteInput({ operation: "order.delete" })),
    (e) => e.code === "CAPABILITY_UNSUPPORTED",
  );
  await assert.rejects(
    () => adapter.invoke(runStub(), noteInput({ changes: { status: "closed" } })),
    (e) => e.code === "INVALID_ARGUMENT",
  );
  await assert.rejects(
    () =>
      adapter.invoke(
        runStub({ requestId: null }),
        noteInput({ idempotencyKey: undefined }),
      ),
    (e) => e.code === "INVALID_ARGUMENT",
  );
  await assert.rejects(
    () =>
      adapter.invoke(
        runStub(),
        noteInput({ changes: { remark: "x".repeat(2001) } }),
      ),
    (e) => e.code === "INVALID_ARGUMENT",
  );
  await assert.rejects(
    () =>
      adapter.invoke(runStub(), {
        operation: "order.update_delivery_date",
        orderNo: "HJY-1",
        changes: { deliveryDate: "2026-13-99" },
        idempotencyKey: "idem-delivery-bad",
      }),
    (e) => e.code === "INVALID_ARGUMENT",
  );
});

test("validates status values", async () => {
  const { ctx } = createCtx(async () => ({ code: 0, data: {} }));
  const adapter = createAdapter(ctx);
  await assert.rejects(
    () =>
      adapter.invoke(runStub(), {
        operation: "order.update_status",
        orderNo: "HJY-1",
        changes: { status: "completed" },
        idempotencyKey: "idem-status",
      }),
    (e) => e.code === "INVALID_ARGUMENT",
  );
});

test("maps backend envelope errors to Hub error codes", async () => {
  assert.equal(mapWriteError(409, "IDEMPOTENCY_CONFLICT: conflict"), "IDEMPOTENCY_CONFLICT");
  assert.equal(mapWriteError(409, "AGENT_BUSY: busy"), "AGENT_BUSY");
  assert.equal(mapWriteError(400, "CAPABILITY_UNSUPPORTED: no"), "CAPABILITY_UNSUPPORTED");
  assert.equal(mapWriteError(404, "订单不存在"), "TARGET_NOT_FOUND");
  assert.equal(mapWriteError(400, "bad input"), "INVALID_ARGUMENT");
});
