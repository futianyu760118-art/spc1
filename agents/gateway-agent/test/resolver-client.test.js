"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { createResolverClient } = require("../src/resolver-client");

function startStub(handler) {
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", () => handler(req, res, body));
  });
  const ready = new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });
  return { ready, close: () => new Promise((resolve) => server.close(resolve)) };
}

test("resolveCaller sends X-Gateway-Token and caller", async () => {
  let captured = null;
  const stub = startStub((req, res, body) => {
    captured = { url: req.url, headers: req.headers, body: JSON.parse(body) };
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ code: 0, data: { mode: "user", agentNo: "AG-000001", actorToken: "tok" } }));
  });
  const port = await stub.ready;
  const client = createResolverClient({
    config: { backendInternalBaseUrl: `http://127.0.0.1:${port}`, gatewayInternalToken: "gw-token" },
    log: () => {},
  });
  const data = await client.resolveCaller({
    runId: "run-1", traceId: "trace-1", capability: "query_control_platform",
    input: { path: "/external/orders/list" },
    caller: { systemId: "aeos-hub", agentId: "AG-000001", userId: "10086", taskId: "AT-000123", traceId: "trace-1" },
  });
  assert.equal(data.actorToken, "tok");
  assert.equal(captured.url, "/api/v1/internal/gateway/resolve-caller");
  assert.equal(captured.headers["x-gateway-token"], "gw-token");
  assert.equal(captured.body.caller.agentId, "AG-000001");
  await stub.close();
});

test("resolveCaller preserves AGENT_NOT_FOUND", async () => {
  const stub = startStub((req, res) => {
    res.writeHead(403, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ code: 403, message: "denied", data: { reason: "AGENT_NOT_FOUND" } }));
  });
  const port = await stub.ready;
  const client = createResolverClient({
    config: { backendInternalBaseUrl: `http://127.0.0.1:${port}`, gatewayInternalToken: "gw-token" },
    log: () => {},
  });
  await assert.rejects(
    () => client.resolveCaller({ runId: "r", capability: "query_control_platform", input: {}, caller: {} }),
    (e) => e.code === "AGENT_NOT_FOUND",
  );
  await stub.close();
});

test("resolveCaller keeps other 403 reasons as INVALID_ARGUMENT", async () => {
  const stub = startStub((req, res) => {
    res.writeHead(403, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ code: 403, message: "denied", data: { reason: "USER_NOT_FOUND" } }));
  });
  const port = await stub.ready;
  const client = createResolverClient({
    config: { backendInternalBaseUrl: `http://127.0.0.1:${port}`, gatewayInternalToken: "gw-token" },
    log: () => {},
  });
  await assert.rejects(
    () => client.resolveCaller({ runId: "r", capability: "query_control_platform", input: {}, caller: {} }),
    (e) => e.code === "INVALID_ARGUMENT",
  );
  await stub.close();
});
