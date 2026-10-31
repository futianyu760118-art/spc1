"use strict";

const path = require("node:path");
const pkg = require("../package.json");
const { runAgent } = require("@spc/execution-agent-runtime");
const { createAdapter } = require("./query-adapter");

runAgent({
  agentKey: "query",
  envPath: path.resolve(__dirname, "..", ".env"),
  defaults: {
    agentId: "runtime-control-platform-query",
    agentName: "公司中台查询智能体",
    agentVersion: pkg.version,
    appKeyEnv: "CONTROL_PLATFORM_QUERY_APP_KEY",
    appSecretEnv: "CONTROL_PLATFORM_QUERY_APP_SECRET",
    configDefaults: { queryTimeoutMs: 15000 },
    envIntDefaults: { CONTROL_PLATFORM_TIMEOUT_MS: "queryTimeoutMs" },
  },
  configMap: {
    agent_name: "agentName",
    ws_url: "wsUrl",
    agent_id: "agentId",
    query_timeout_ms: "queryTimeoutMs",
    log_level: "logLevel",
  },
  createAdapter,
}).catch((e) => {
  console.error(JSON.stringify({ level: "error", event: "agent_start_failed", message: e.message }));
  process.exit(1);
});
