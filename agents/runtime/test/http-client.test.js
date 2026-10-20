"use strict";

const http = require("node:http");
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  createHttpClient,
  UpstreamError,
  mapCode,
  unwrapEnvelope,
  buildQueryString,
} = require("../src/http-client");

test("mapCode maps contract status codes", () => {
  assert.equal(mapCode(400), "INVALID_ARGUMENT");
  assert.equal(mapCode(404), "NOT_FOUND");
  assert.equal(mapCode(429), "RATE_LIMITED");
  assert.equal(mapCode(504), "UPSTREAM_TIMEOUT");
  assert.equal(mapCode(500), "UPSTREAM_UNAVAILABLE");
});

test("unwrapEnvelope returns data for success and throws for business errors", () => {
  assert.deepEqual(unwrapEnvelope({ code: 0, data: { items: [] } }), { items: [] });
  assert.throws(
    () => unwrapEnvelope({ code: 404, message: "not found" }),
    (e) => e instanceof UpstreamError && e.code === "NOT_FOUND",
  );
});

test("buildQueryString skips empty values and preserves order", () => {
  assert.equal(buildQueryString({ agent: "query", page: 1, empty: "" }), "agent=query&page=1");
});

test("signedGet rejects immediately when the signal is already aborted", async () => {
  const controller = new AbortController();
  controller.abort();
  const client = createHttpClient(
    { platformBaseUrl: "http://127.0.0.1:1", appKey: "ak", appSecret: "sk" },
    () => {},
  );

  await assert.rejects(
    client.signedGet("/external/orders/list", "orders.list", {}, { signal: controller.signal }),
    (e) => e instanceof UpstreamError && e.code === "ABORTED",
  );
});

test("signedSendEnvelope PUT merges extra headers and unwraps nothing", async () => {
  const requests = [];
  const server = http.createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk) => { raw += chunk; });
    req.on("end", () => {
      requests.push({ method: req.method, url: req.url, headers: req.headers, body: JSON.parse(raw) });
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ code: 0, message: "success", data: { ok: true } }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  try {
    const client = createHttpClient(
      { platformBaseUrl: `http://127.0.0.1:${port}/api/v1`, appKey: "ak", appSecret: "sk" },
      () => {},
    );
    const envelope = await client.signedSendEnvelope(
      "PUT",
      "/external/orders/O-1/schedule",
      "orders.schedule.update",
      { fields: { shipping_plan: null } },
      { headers: { "X-Agent-Run-Id": "run-9" }, timeoutMs: 5000 },
    );
    assert.deepEqual(envelope, { code: 0, message: "success", data: { ok: true } });
    assert.equal(requests[0].method, "PUT");
    assert.equal(requests[0].url, "/api/v1/external/orders/O-1/schedule");
    assert.equal(requests[0].headers["x-agent-run-id"], "run-9");
    assert.ok(requests[0].headers["x-signature"]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
