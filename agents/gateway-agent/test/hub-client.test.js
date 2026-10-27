"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { createHubClient } = require("../src/hub-client");

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

test("borrow/catalog/assistant-events use Hub auth headers and paths", async () => {
  const calls = [];
  const stub = startStub((req, res, body) => {
    calls.push({ method: req.method, url: req.url, headers: req.headers, body: body ? JSON.parse(body) : null });
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ accepted: true, templates: [], invocation: { borrowOrderId: "borrow-1" } }));
  });
  const port = await stub.ready;
  const client = createHubClient({
    config: {
      hubBaseUrl: `http://127.0.0.1:${port}`,
      hubSystemId: "control-platform",
      hubSystemToken: "system-token",
    },
    log: () => {},
  });
  await client.postBorrowOrder({ requestId: "r1", capability: "query_plm", toSystem: "plm", input: {} });
  await client.getBorrowOrder("borrow-1");
  await client.getCatalog();
  await client.postAssistantEvent({ eventId: "e1", traceId: "s1" });
  assert.equal(calls[0].url, "/api/system/borrow-orders");
  assert.equal(calls[1].url, "/api/system/borrow-orders/borrow-1");
  assert.equal(calls[2].url, "/api/system/capability-invocations");
  assert.equal(calls[3].url, "/api/system/assistant-events");
  assert.equal(calls[0].headers["x-aeos-system-id"], "control-platform");
  assert.equal(calls[0].headers["x-aeos-system-token"], "system-token");
  await stub.close();
});

test("postBorrowOrder injects systemId, keeps five caller fields and rejects systemId mismatch", async () => {
  const calls = [];
  const stub = startStub((req, res, body) => {
    calls.push({ url: req.url, body: body ? JSON.parse(body) : null });
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ invocation: { borrowOrderId: "borrow-2" } }));
  });
  const port = await stub.ready;
  const client = createHubClient({
    config: {
      hubBaseUrl: `http://127.0.0.1:${port}`,
      hubSystemId: "control-platform",
      hubSystemToken: "system-token",
    },
    log: () => {},
  });

  const ok = await client.postBorrowOrder({
    requestId: "r2", capability: "query_plm", toSystem: "plm", input: {},
    caller: { agentId: "AG-000001", userId: "10086", taskId: "AT-000123", traceId: "trace-2", token: "leak" },
  });
  assert.equal(ok.status, 200);
  assert.deepEqual(calls[0].body.caller, {
    systemId: "control-platform", agentId: "AG-000001", userId: "10086",
    taskId: "AT-000123", traceId: "trace-2",
  });

  const rejected = await client.postBorrowOrder({
    requestId: "r3", capability: "query_plm", toSystem: "plm", input: {},
    caller: { systemId: "other-platform", agentId: "AG-000001" },
  });
  assert.equal(rejected.status, 400);
  assert.equal(rejected.body.code, "INVALID_ARGUMENT");
  assert.equal(calls.length, 1);
  await stub.close();
});
