"use strict";

const path = require("node:path");
const pkg = require("../package.json");
const { runAgent } = require("@spc/execution-agent-runtime");
const { createAdapter } = require("./reasoning-adapter");

runAgent({
  agentKey: "reasoning",
  envPath: path.resolve(__dirname, "..", ".env"),
  defaults: {
    agentId: "runtime-control-platform-reasoning",
    agentName: "公司中台推理智能体",
    agentVersion: pkg.version,
    appKeyEnv: "CONTROL_PLATFORM_REASONING_APP_KEY",
    appSecretEnv: "CONTROL_PLATFORM_REASONING_APP_SECRET",
    configDefaults: { reasoningTimeoutMs: 180000 },
    envIntDefaults: { CONTROL_PLATFORM_REASONING_TIMEOUT_MS: "reasoningTimeoutMs" },
  },
  configMap: {
    agent_name: "agentName",
    ws_url: "wsUrl",
    agent_id: "agentId",
    reasoning_timeout_ms: "reasoningTimeoutMs",
    log_level: "logLevel",
  },
  createAdapter,
}).catch((e) => {
  console.error(JSON.stringify({ level: "error", event: "agent_start_failed", message: e.message }));
  process.exit(1);
});
