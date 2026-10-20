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
    connection: { isRegistered: () => true, activeRun: null },
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
    connection: { isRegistered: () => true, activeRun: null },
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

test("admin run returns 409 while hub dispatch occupies activeRun", async () => {
  const port = await getFreePort();
  const config = { healthCheckPort: port, adminToken: "tok", configVersion: 0, agentId: "a" };
  const server = startHealthServer({
    config,
    log: () => {},
    connection: { isRegistered: () => true, activeRun: { runId: "hub-run-1" } },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async () => ({}),
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const busy = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({ capability: "query_control_platform", input: { path: "/common/ping" } }),
    });
    assert.equal(busy.status, 409);
    assert.equal((await busy.json()).status, "busy");
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
    connection: { isRegistered: () => true, activeRun: null },
    capabilities: [{ name: "query_control_platform" }],
    agentKey: "query",
    onLocalRun: async (runId, capability, input) => {
      calls.push({ runId, capability, input });
      return { items: [], total: 0 };
    },
  });
  if (!server.listening) await once(server, "listening");
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const res = await fetch(`${baseUrl}/admin/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-admin-token": "tok" },
      body: JSON.stringify({
        runId: "local-1",
        capability: "query_control_platform",
        input: { path: "/common/ping", params: {} },
      }),
    });
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.equal(body.ok, true);
    assert.equal(body.runId, "local-1");
    assert.deepEqual(body.result, { items: [], total: 0 });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].capability, "query_control_platform");
    assert.deepEqual(calls[0].input, { path: "/common/ping", params: {} });
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
    connection: { isRegistered: () => true, activeRun: null },
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
      body: JSON.stringify({ capability: "query_control_platform", input: { path: "/x" } }),
    });
    assert.equal(res.status, 500);
    const body = await res.json();
    assert.equal(body.ok, false);
    assert.equal(body.code, "INVALID_ARGUMENT");
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
