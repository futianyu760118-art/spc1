"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");
const { once } = require("node:events");
const { startHealthServer } = require("../src/health-server");

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

test("health server exposes healthz and token-protected admin status", async () => {
  const port = await getFreePort();
  const config = {
    healthCheckPort: port,
    adminToken: "admin-é",
    configVersion: 3,
    agentId: "agent-1",
  };
  const server = startHealthServer({
    config,
    log: () => {},
    connection: {
      isRegistered: () => true,
      hubRun: null,
      localRuns: new Map([["local-1", { runId: "local-1" }]]),
    },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;

  try {
    const health = await fetch(`${baseUrl}/healthz`);
    assert.equal(health.status, 200);
    assert.deepEqual(await health.json(), { status: "ok" });

    const unauthorized = await fetch(`${baseUrl}/admin/status`);
    assert.equal(unauthorized.status, 401);

    const wrongToken = await fetch(`${baseUrl}/admin/status`, { headers: { "x-admin-token": "admin-e" } });
    assert.equal(wrongToken.status, 401);

    const status = await fetch(`${baseUrl}/admin/status`, { headers: { "x-admin-token": "admin-é" } });
    assert.equal(status.status, 200);
    const body = await status.json();
    assert.equal(body.agentKey, "query");
    assert.equal(body.currentRunId, "local-1");
    assert.deepEqual(body.capabilities, ["query_control_platform"]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("admin run requires token and rejects unknown capability", async () => {
  const port = await getFreePort();
  const config = { healthCheckPort: port, adminToken: "tok", configVersion: 0, agentId: "a" };
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async () => ({}),
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const noToken = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capability: "query_control_platform", input: {} }),
    });
    assert.equal(noToken.status, 401);

    const unknown = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({ capability: "nope", input: {} }),
    });
    assert.equal(unknown.status, 400);
    assert.equal((await unknown.json()).status, "unknown_capability");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("admin run stays available while a hub dispatch occupies hubRun", async () => {
  const port = await getFreePort();
  const config = { healthCheckPort: port, adminToken: "tok", configVersion: 0, agentId: "a" };
  let invoked = false;
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: { runId: "hub-run-1" } },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async () => {
      invoked = true;
      return { ok: true };
    },
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const res = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({
        capability: "query_control_platform",
        input: { path: "/common/ping" },
        actorToken: "actor-test",
      }),
    });
    assert.equal(res.status, 200);
    assert.equal((await res.json()).ok, true);
    assert.equal(invoked, true);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("admin run invokes onLocalRun and returns result", async () => {
  const port = await getFreePort();
  const config = { healthCheckPort: port, adminToken: "tok", configVersion: 0, agentId: "a" };
  const calls = [];
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async (context) => {
      calls.push(context);
      return { items: [], total: 0 };
    },
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const missing = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({
        runId: "local-1",
        capability: "query_control_platform",
        input: { path: "/common/ping", params: {} },
      }),
    });
    assert.equal(missing.status, 400);
    assert.equal((await missing.json()).status, "missing_actor_token");

    const res = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({
        runId: "local-1",
        capability: "query_control_platform",
        input: { path: "/common/ping", params: {} },
        operator: { user_id: "462" },
        actorToken: "actor-test",
        traceId: "trace-local",
        request_id: "req-local",
        target_agent_ref: "spc-agent-query",
        caller: { systemId: "control-platform", agentId: "AG-000001", taskId: "AT-000123" },
      }),
    });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.ok, true);
    assert.equal(body.runId, "local-1");
    assert.deepEqual(body.result, { items: [], total: 0 });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].runId, "local-1");
    assert.equal(calls[0].capability, "query_control_platform");
    assert.deepEqual(calls[0].input, { path: "/common/ping", params: {} });
    assert.deepEqual(calls[0].operator, { user_id: "462" });
    assert.equal(calls[0].actorToken, "actor-test");
    assert.equal(calls[0].traceId, "trace-local");
    assert.equal(calls[0].requestId, "req-local");
    assert.equal(calls[0].targetAgentRef, "spc-agent-query");
    assert.deepEqual(calls[0].caller, { systemId: "control-platform", agentId: "AG-000001", taskId: "AT-000123" });
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("internal hub proxy requires the gateway token and delegates the request", async () => {
  const port = await getFreePort();
  const config = {
    healthCheckPort: port,
    adminToken: "tok",
    gatewayInternalToken: "gw-token",
    configVersion: 0,
    agentId: "gateway",
  };
  const proxied = [];
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "gateway",
    onHubProxy: async (req, res, pathname, send) => {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      proxied.push({ method: req.method, pathname, body: Buffer.concat(chunks).toString("utf8") });
      send(200, { ok: true });
    },
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const unauthorized = await fetch(`${baseUrl}/internal/hub/capability-invocations`);
    assert.equal(unauthorized.status, 401);

    const res = await fetch(`${baseUrl}/internal/hub/assistant-events`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-gateway-token": "gw-token" },
      body: JSON.stringify({ eventId: "e1" }),
    });
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { ok: true });
    assert.deepEqual(proxied, [
      { method: "POST", pathname: "/internal/hub/assistant-events", body: '{"eventId":"e1"}' },
    ]);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("internal hub proxy returns 503 when no proxy hook is configured", async () => {
  const port = await getFreePort();
  const config = {
    healthCheckPort: port,
    adminToken: "tok",
    gatewayInternalToken: "gw-token",
    configVersion: 0,
    agentId: "query",
  };
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const res = await fetch(`${baseUrl}/internal/hub/capability-invocations`, {
      headers: { "x-gateway-token": "gw-token" },
    });
    assert.equal(res.status, 503);
    assert.equal((await res.json()).status, "proxy_disabled");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("admin run maps adapter failure to 500 with code", async () => {
  const port = await getFreePort();
  const config = { healthCheckPort: port, adminToken: "tok", configVersion: 0, agentId: "a" };
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async () => {
      const err = new Error("path 不在白名单");
      err.code = "INVALID_ARGUMENT";
      throw err;
    },
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const res = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({
        capability: "query_control_platform",
        input: { path: "/x" },
        actorToken: "actor-test",
      }),
    });
    assert.equal(res.status, 500);
    const body = await res.json();
    assert.equal(body.ok, false);
    assert.equal(body.code, "INVALID_ARGUMENT");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test("admin run rejects non-string target_agent_ref", async () => {
  const port = await getFreePort();
  const config = { healthCheckPort: port, adminToken: "tok", configVersion: 0, agentId: "a" };
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, hubRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async () => ({}),
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const res = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({
        capability: "query_control_platform",
        input: {},
        actorToken: "actor-test",
        target_agent_ref: 123,
      }),
    });
    assert.equal(res.status, 400);
    assert.equal((await res.json()).status, "invalid_target_agent_ref");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
