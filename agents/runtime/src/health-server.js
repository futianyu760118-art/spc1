"use strict";

const crypto = require("node:crypto");
const http = require("node:http");
const { normalizeRequestId, normalizeTargetAgentRef } = require("./run-context");

const MAX_BODY_BYTES = 1024 * 1024;

function tokenMatches(provided, expected) {
  if (!expected || typeof provided !== "string") return false;
  const providedBuf = Buffer.from(provided);
  const expectedBuf = Buffer.from(expected);
  return providedBuf.length === expectedBuf.length && crypto.timingSafeEqual(providedBuf, expectedBuf);
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("body_too_large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (chunks.length === 0) return resolve({});
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(new Error("bad_json"));
      }
    });
    req.on("error", reject);
  });
}

async function handleLocalRun(req, res, { log, capabilities, onLocalRun }) {
  const send = (status, body) => {
    if (res.writableEnded) return;
    res.writeHead(status, { "Content-Type": "application/json" });
    res.end(JSON.stringify(body));
  };
  let body;
  try {
    body = await readJsonBody(req);
  } catch (e) {
    send(400, { status: e.message === "bad_json" ? "bad_json" : "body_too_large" });
    return;
  }
  const capability = body && typeof body === "object" ? body.capability : undefined;
  const input = body && typeof body === "object" ? body.input : undefined;
  const operator = body && typeof body === "object" && body.operator && typeof body.operator === "object"
    ? body.operator
    : null;
  const actorToken = body && typeof body === "object" && typeof body.actorToken === "string"
    ? body.actorToken
    : null;
  const traceId = body && typeof body === "object" && typeof body.traceId === "string"
    ? body.traceId
    : "";
  const caller = body && typeof body === "object" && body.caller && typeof body.caller === "object"
    ? body.caller
    : null;
  const requestId = normalizeRequestId(body);
  let targetAgentRef;
  try {
    targetAgentRef = normalizeTargetAgentRef(body);
  } catch (e) {
    send(400, { status: "invalid_target_agent_ref", message: e.message });
    return;
  }
  if (typeof capability !== "string" || !capabilities.some((c) => c.name === capability)) {
    send(400, { status: "unknown_capability" });
    return;
  }
  if (input === undefined || input === null || typeof input !== "object" || Array.isArray(input)) {
    send(400, { status: "bad_input" });
    return;
  }
  if (!actorToken) {
    send(400, { status: "missing_actor_token" });
    return;
  }
  if (typeof onLocalRun !== "function") {
    send(503, { status: "local_run_disabled" });
    return;
  }
  const runId =
    typeof body.runId === "string" && body.runId.trim() ? body.runId.trim() : `local-${crypto.randomUUID()}`;
  log("info", "local_run_started", { runId, capability, requestId, targetAgentRef });
  try {
    const result = await onLocalRun({
      runId,
      capability,
      input,
      requestId,
      traceId,
      caller,
      targetAgentRef,
      operator,
      actorToken,
    });
    send(200, { ok: true, runId, result: result ?? {} });
  } catch (e) {
    log("info", "local_run_failed", {
      runId,
      capability,
      code: e && e.code,
      message: e && e.message ? e.message : String(e),
    });
    send(500, {
      ok: false,
      runId,
      code: (e && e.code) || "INTERNAL_ERROR",
      message: (e && e.message) || "执行失败",
    });
  }
}

function startHealthServer({ config, log, connection, capabilities, agentKey, onLocalRun, onHubProxy }) {
  if (config.healthCheckPort <= 0) return null;
  const server = http.createServer((req, res) => {
    const pathname = req.url ? req.url.split("?")[0] : "";
    const send = (status, body) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(body));
    };
    if (pathname === "/healthz") {
      const ok = connection.isRegistered();
      send(ok ? 200 : 503, { status: ok ? "ok" : "not_registered" });
      return;
    }
    if (pathname.startsWith("/internal/hub/")) {
      if (typeof onHubProxy !== "function") {
        send(503, { status: "proxy_disabled" });
        return;
      }
      if (!tokenMatches(req.headers["x-gateway-token"], config.gatewayInternalToken)) {
        send(401, { status: "unauthorized" });
        return;
      }
      Promise.resolve(onHubProxy(req, res, pathname, send)).catch((e) => {
        log("error", "hub_proxy_failed", { message: e.message, path: pathname });
        if (!res.writableEnded) send(500, { status: "internal_error" });
      });
      return;
    }
    if (!pathname.startsWith("/admin/")) {
      send(404, { status: "not_found" });
      return;
    }
    if (!config.adminToken) {
      send(503, { status: "admin_disabled" });
      return;
    }
    if (!tokenMatches(req.headers["x-admin-token"], config.adminToken)) {
      send(401, { status: "unauthorized" });
      return;
    }
    if (pathname === "/admin/status" && req.method === "GET") {
      const localRun = connection.localRuns ? connection.localRuns.values().next().value : null;
      const currentRun = connection.hubRun || localRun || null;
      send(200, {
        registered: connection.isRegistered(),
        currentRunId: currentRun ? currentRun.runId : null,
        configVersion: config.configVersion,
        uptimeS: Math.floor(process.uptime()),
        agentKey,
        agentId: config.agentId,
        capabilities: capabilities.map((c) => c.name),
      });
      return;
    }
    if (pathname === "/admin/restart" && req.method === "POST") {
      send(200, { status: "restarting" });
      log("info", "admin_restart_requested", { agentKey });
      setTimeout(() => process.exit(0), 150);
      return;
    }
    if (pathname === "/admin/run" && req.method === "POST") {
      handleLocalRun(req, res, { log, capabilities, onLocalRun }).catch((e) => {
        log("error", "local_run_handler_error", { message: e.message });
        if (!res.writableEnded) send(500, { status: "internal_error" });
      });
      return;
    }
    send(404, { status: "not_found" });
  });
  server.on("error", (err) => log("error", "health_server_error", { message: err.message }));
  server.listen(config.healthCheckPort, "0.0.0.0");
  log("info", "health_server_listening", { port: config.healthCheckPort, bind: "0.0.0.0", agentKey });
  return server;
}

module.exports = { startHealthServer, readJsonBody };
