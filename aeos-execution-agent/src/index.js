"use strict";

const http = require("node:http");
const config = require("./config");
const { log } = require("./lib/http-client");
const { HubConnection } = require("./protocol");
const queryAdapter = require("./adapters/query-adapter");
const reasoningAdapter = require("./adapters/reasoning-adapter");

const handlers = {
  // 能力自描述（管理面 127b013 起强校验）：readOnly 只读约束 + constraints 行为保证 +
  // JSON Schema 输入输出声明，缺失会被派单校验拒绝（WRITE_FORBIDDEN）；
  // reasoning 的 requireEvidence=true：结论缺证据引用时降级低置信度（管理面补充要求）
  capabilities: [
    {
      name: "query_control_platform",
      description: "中台只读查询（契约 §4.2 冻结白名单）",
      readOnly: true,
      constraints: { readOnly: true },
      inputSchema: queryAdapter.inputSchema,
      outputSchema: queryAdapter.outputSchema,
    },
    {
      name: "reason_control_platform",
      description: "中台只读推理（大模型分析，结论带 evidence_refs）",
      readOnly: true,
      constraints: { readOnly: true, requireEvidence: true },
      inputSchema: reasoningAdapter.inputSchema,
      outputSchema: reasoningAdapter.outputSchema,
    },
  ],

  /** dispatch 路由；run.controller.signal 透传给上游请求，召回/断线即中止 */
  async onDispatch(run, input) {
    if (run.capability === "query_control_platform") {
      return queryAdapter.invoke(input);
    }
    if (run.capability === "reason_control_platform") {
      // null = 召回/取消，protocol 层据此不回报
      return reasoningAdapter.invoke(run.runId, input, run.controller.signal);
    }
    throw Object.assign(new Error(`能力未注册：${run.capability}`), { code: "INVALID_ARGUMENT" });
  },

  /** 召回/断线：本地已由 run.controller.abort() 中止；推理任务额外通知中台同步取消（不回报） */
  onRecall(runId) {
    Promise.resolve(reasoningAdapter.cancel(runId)).catch((e) => {
      if (e.code !== "ABORTED") log("warn", "reasoning_cancel_failed", { runId, message: e.message });
    });
  },
};

function startHealthServer(connection) {
  if (config.healthCheckPort <= 0) return null;
  const server = http.createServer((req, res) => {
    if (req.url && req.url.split("?")[0] === "/healthz") {
      const ok = connection.isRegistered();
      res.writeHead(ok ? 200 : 503, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: ok ? "ok" : "not_registered" }));
    } else {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "not_found" }));
    }
  });
  server.on("error", (err) => log("error", "health_server_error", { message: err.message }));
  server.listen(config.healthCheckPort, "127.0.0.1");
  log("info", "health_server_listening", { port: config.healthCheckPort });
  return server;
}

function main() {
  log("info", "agent_starting", {
    agentId: config.agentId,
    hub: config.wsUrl,
    platform: config.platformBaseUrl,
    query_paths: Object.keys(queryAdapter.PATH_ENDPOINT_CODES).length,
  });
  const connection = new HubConnection(handlers);
  const healthServer = startHealthServer(connection);
  connection.start();

  const shutdown = (signal) => {
    log("info", "agent_stopping", { signal });
    connection.stop();
    if (healthServer) healthServer.close();
    setTimeout(() => process.exit(0), 2000).unref();
  };
  process.on("SIGINT", () => shutdown("SIGINT"));
  process.on("SIGTERM", () => shutdown("SIGTERM"));
  if (process.channel) {
    process.on("message", (message) => {
      if (message && message.type === "shutdown") shutdown("ipc");
    });
  }
  process.on("uncaughtException", (err) => {
    log("error", "uncaught_exception", { message: err.message, stack: err.stack });
    process.exit(1);
  });
  process.on("unhandledRejection", (reason) => {
    log("error", "unhandled_rejection", { reason: String(reason) });
    process.exit(1);
  });
}

main();
