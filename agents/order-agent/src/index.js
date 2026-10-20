"use strict";

const path = require("node:path");
const pkg = require("../package.json");
const { runAgent } = require("@spc/execution-agent-runtime");
const { createAdapter } = require("./order-adapter");

runAgent({
  agentKey: "order",
  envPath: path.resolve(__dirname, "..", ".env"),
  defaults: {
    agentId: "runtime-control-platform-order",
    agentName: "公司中台订单智能体",
    agentVersion: pkg.version,
    appKeyEnv: "CONTROL_PLATFORM_ORDER_APP_KEY",
    appSecretEnv: "CONTROL_PLATFORM_ORDER_APP_SECRET",
    configDefaults: { writeTimeoutMs: 15000 },
    envIntDefaults: { CONTROL_PLATFORM_TIMEOUT_MS: "writeTimeoutMs" },
  },
  configMap: {
    agent_name: "agentName",
    ws_url: "wsUrl",
    agent_id: "agentId",
    write_timeout_ms: "writeTimeoutMs",
    log_level: "logLevel",
  },
  createAdapter,
}).catch((e) => {
  console.error(JSON.stringify({ level: "error", event: "agent_start_failed", message: e.message }));
  process.exit(1);
});
