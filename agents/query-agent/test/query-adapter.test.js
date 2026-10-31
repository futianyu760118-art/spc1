"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { UpstreamError } = require("@spc/execution-agent-runtime");
const { createAdapter, PATH_ENDPOINT_CODES } = require("../src/query-adapter");

function createCtx(signedGet = async () => ({ items: [{ id: 1 }] })) {
  const calls = [];
  return {
    calls,
    ctx: {
      config: { queryTimeoutMs: 1234 },
      log: () => {},
      http: {
        signedGet: async (...args) => {
          calls.push(args);
          return signedGet(...args);
        },
      },
    },
  };
}

function createRun() {
  const events = [];
  return {
    events,
    run: {
      controller: new AbortController(),
      report: (...args) => events.push(args),
    },
  };
}

test("declares the read-only query capability", () => {
  const { ctx } = createCtx();
  const { capability } = createAdapter(ctx);
  assert.equal(capability.name, "query_control_platform");
  assert.equal(capability.readOnly, true);
  assert.deepEqual(capability.constraints, { readOnly: true });
});

test("rejects path outside the frozen whitelist", async () => {
  const { ctx } = createCtx();
  const adapter = createAdapter(ctx);
  const { run } = createRun();
  await assert.rejects(
    () => adapter.invoke(run, { path: "/invalid" }),
    (e) => e.code === "INVALID_ARGUMENT",
  );
});

test("maps path to endpoint code, forwards params untouched and passes timeout", async () => {
  const { ctx, calls } = createCtx();
  const adapter = createAdapter(ctx);
  const { run } = createRun();
  const params = { page: 1, keyword: "SO-1" };
  const result = await adapter.invoke(run, { path: "/external/orders/list", params });

  assert.deepEqual(result, { items: [{ id: 1 }] });
  assert.equal(calls[0][0], "/external/orders/list");
  assert.equal(calls[0][1], PATH_ENDPOINT_CODES["/external/orders/list"]);
  assert.equal(calls[0][2], params);
  assert.equal(calls[0][3].timeoutMs, 1234);
});

test("propagates the upstream error code and reports step_started plus error", async () => {
  const { ctx } = createCtx(async () => {
    throw new UpstreamError("UPSTREAM_TIMEOUT", "中台响应超时");
  });
  const adapter = createAdapter(ctx);
  const { run, events } = createRun();

  await assert.rejects(
    () => adapter.invoke(run, { path: "/external/orders/list", params: { page: 1 } }),
    (e) => e.code === "UPSTREAM_TIMEOUT",
  );

  assert.deepEqual(events.map(([event]) => event), ["step_started", "error"]);
  assert.equal(events[1][4].code, "UPSTREAM_TIMEOUT");
});
