"use strict";

const crypto = require("node:crypto");
const http = require("node:http");

const MAX_BODY_BYTES = 1024 * 1024;

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

async function handleLocalRun(req, res, { log, connection, capabilities, onLocalRun }) {
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
  if (typeof capability !== "string" || !capabilities.some((c) => c.name === capability)) {
    send(400, { status: "unknown_capability" });
    return;
  }
  if (input === undefined || input === null || typeof input !== "object" || Array.isArray(input)) {
    send(400, { status: "bad_input" });
    return;
  }
  if (connection.activeRun) {
    send(409, { status: "busy" });
    return;
  }
  if (typeof onLocalRun !== "function") {
    send(503, { status: "local_run_disabled" });
    return;
  }
  const runId =
    typeof body.runId === "string" && body.runId.trim() ? body.runId.trim() : `local-${crypto.randomUUID()}`;
  log("info", "local_run_started", { runId, capability });
  try {
    const result = await onLocalRun(runId, capability, input, operator);
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

function startHealthServer({ config, log, connection, capabilities, agentKey, onLocalRun }) {
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
    if (!pathname.startsWith("/admin/")) {
      send(404, { status: "not_found" });
      return;
    }
    if (!config.adminToken) {
      send(503, { status: "admin_disabled" });
      return;
    }
    const token = req.headers["x-admin-token"];
    if (typeof token !== "string") {
      send(401, { status: "unauthorized" });
      return;
    }
    const tokenBuf = Buffer.from(token);
    const adminBuf = Buffer.from(config.adminToken);
    if (tokenBuf.length !== adminBuf.length || !crypto.timingSafeEqual(tokenBuf, adminBuf)) {
      send(401, { status: "unauthorized" });
      return;
    }
    if (pathname === "/admin/status" && req.method === "GET") {
      send(200, {
        registered: connection.isRegistered(),
        currentRunId: connection.activeRun ? connection.activeRun.runId : null,
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
      handleLocalRun(req, res, { log, connection, capabilities, onLocalRun }).catch((e) => {
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

module.exports = { startHealthServer };
