"use strict";

const http = require("node:http");
const { spawn } = require("node:child_process");

const API_PREFIX = "/api/v1";
const WAIT_INTERVAL_MS = 25;
const KILL_GRACE_MS = 3000;

function normalizePath(url) {
  const pathname = (url || "").split("?")[0];
  if (pathname.startsWith(API_PREFIX)) return pathname.slice(API_PREFIX.length) || "/";
  return pathname;
}

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

function startStubPlatform({
  config = {},
  queryData = { items: [] },
  reasoningData = {},
  orderData = null,
  queryDelayMs = 0,
} = {}) {
  const requests = [];
  const server = http.createServer((req, res) => {
    const path = normalizePath(req.url);
    let body = "";
    req.on("data", (chunk) => { body += chunk.toString(); });
    req.on("end", () => {
      let parsedBody = null;
      try {
        parsedBody = body ? JSON.parse(body) : null;
      } catch {
        parsedBody = null;
      }
      requests.push({ method: req.method, path, url: req.url, body: parsedBody });
      if (req.method === "GET" && path === "/external/agent/config") {
        sendJson(res, 200, { code: 0, data: { version: 1, config } });
        return;
      }
      if (req.method === "GET" && path === "/common/ping") {
        sendJson(res, 200, { code: 0, data: { ok: true } });
        return;
      }
      if (req.method === "POST" && path === "/internal/gateway/resolve-caller") {
        const payload = parsedBody || {};
        const caller = payload.caller || {};
        if (caller.agentId === "AG-REJECT") {
          sendJson(res, 403, { code: 403, message: "agent not found", data: { reason: "AGENT_NOT_FOUND" } });
          return;
        }
        sendJson(res, 200, { code: 0, message: "ok", data: { mode: "system", actorToken: null } });
        return;
      }
      if (req.method === "GET" && path === "/external/orders/list") {
        const respond = () => sendJson(res, 200, { code: 0, data: queryData });
        if (queryDelayMs > 0) setTimeout(respond, queryDelayMs);
        else respond();
        return;
      }
      if (req.method === "POST" && path === "/external/reasoning/analyze") {
        sendJson(res, 200, { code: 0, data: reasoningData });
        return;
      }
      if (req.method === "PUT" && path.startsWith("/external/orders/") && path.endsWith("/schedule") && orderData !== null) {
        sendJson(res, 200, { code: 0, data: orderData });
        return;
      }
      sendJson(res, 404, { code: 404, message: "not found" });
    });
  });

  const ready = new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", reject);
      resolve(server.address().port);
    });
  });

  return {
    ready,
    requests,
    async close() {
      const closed = new Promise((resolve) => server.close(resolve));
      server.closeAllConnections();
      await closed;
    },
  };
}

function spawnAgent({ entry, env = {} }) {
  const child = spawn(process.execPath, [entry], {
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const logs = [];
  child.stdout.on("data", (chunk) => logs.push(chunk.toString()));
  child.stderr.on("data", (chunk) => logs.push(chunk.toString()));
  child.on("error", (e) => logs.push(`spawn error: ${e.message}\n`));
  const exited = new Promise((resolve) => {
    child.once("close", (code, signal) => resolve({ code, signal }));
  });
  return { child, logs, exited };
}

async function waitUntil(predicate, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (await predicate()) return;
    if (Date.now() >= deadline) throw new Error(`waitUntil 超时（${timeoutMs}ms）`);
    await new Promise((resolve) => setTimeout(resolve, WAIT_INTERVAL_MS));
  }
}

async function stopAgent(agent) {
  const { child, exited } = agent;
  if (child.exitCode !== null || child.signalCode !== null) return exited;

  child.kill("SIGTERM");
  const killTimer = setTimeout(() => {
    if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
  }, KILL_GRACE_MS);
  killTimer.unref();
  try {
    await exited;
  } finally {
    clearTimeout(killTimer);
  }
}

module.exports = { startStubPlatform, spawnAgent, waitUntil, stopAgent };
