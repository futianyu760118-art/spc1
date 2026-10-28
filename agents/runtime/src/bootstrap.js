"use strict";

const { createConfig } = require("./config");
const { createLogger } = require("./logger");
const { createHttpClient } = require("./http-client");
const { createRemoteConfig } = require("./remote-config");
const { HubConnection } = require("./protocol");
const { startHealthServer } = require("./health-server");
const { buildRunContext } = require("./run-context");

function safeCancel(adapter, config, log) {
  return (runId) => {
    if (!adapter.cancel) return;
    Promise.resolve()
      .then(() => adapter.cancel(runId))
      .catch((e) => {
        log("warn", "adapter_cancel_failed", {
          agentKey: config.agentKey,
          runId,
          code: e && e.code,
          message: e && e.message ? e.message : String(e),
        });
      });
  };
}

function createLocalRunHandler(adapter, connection, log) {
  return async (context) => {
    const run = buildRunContext({
      ...context,
      source: "local",
      report: (event, name, status, summary, detail, timings) =>
        log("info", "local_run_event", {
          runId: context.runId,
          event,
          name,
          status,
          summary,
          detail,
          timings,
        }),
    });
    connection.localRuns.set(run.runId, run);
    try {
      return await adapter.invoke(run, run.input);
    } finally {
      connection.localRuns.delete(run.runId);
    }
  };
}

async function startAgent({ agentKey, envPath, defaults, configMap, createAdapter }) {
  const config = createConfig({ agentKey, envPath, defaults });
  const log = createLogger(() => config.logLevel);
  const http = createHttpClient(config, log);
  const remote = createRemoteConfig({ config, configMap, http, log });
  await remote.applyRemoteConfigWithRetry();

  const adapter = createAdapter({ config, http, log });
  const handlers = {
    capabilities: [adapter.capability],
    onDispatch: (run, input) => adapter.invoke(run, input),
    onRecall: safeCancel(adapter, config, log),
  };
  const connection = new HubConnection({ config, log, handlers });
  const healthServer = startHealthServer({
    config,
    log,
    connection,
    capabilities: handlers.capabilities,
    agentKey: config.agentKey,
    onLocalRun: createLocalRunHandler(adapter, connection, log),
  });
  connection.start();
  log("info", "agent_starting", {
    agentKey: config.agentKey,
    agentId: config.agentId,
    hub: config.wsUrl,
  });
  return { config, log, connection, healthServer };
}

async function runAgent(options) {
  const started = await startAgent(options);
  const { config, log, connection, healthServer } = started;

  const shutdown = (signal) => {
    log("info", "agent_stopping", { signal, agentKey: config.agentKey });
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
  return started;
}

module.exports = { startAgent, runAgent, safeCancel, createLocalRunHandler };
