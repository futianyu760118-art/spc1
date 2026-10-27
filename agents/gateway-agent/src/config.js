"use strict";

const path = require("node:path");
const { createConfig } = require("@spc/execution-agent-runtime");

function buildConfigs() {
  const gateway = createConfig({
    agentKey: "gateway",
    envPath: path.resolve(__dirname, "..", ".env"),
    defaults: {
      agentId: "gateway-control-platform",
      agentName: "公司中台系统网关",
      agentVersion: require("../package.json").version,
      appKeyEnv: "CONTROL_PLATFORM_QUERY_APP_KEY",
      appSecretEnv: "CONTROL_PLATFORM_QUERY_APP_SECRET",
      configDefaults: { queryTimeoutMs: 15000, reasoningTimeoutMs: 180000 },
    },
  });

  const query = createConfig({
    agentKey: "query",
    envPath: path.resolve(__dirname, "..", ".env"),
    defaults: {
      agentId: "gateway-control-platform",
      agentName: "查询适配器",
      agentVersion: gateway.agentVersion,
      appKeyEnv: "CONTROL_PLATFORM_QUERY_APP_KEY",
      appSecretEnv: "CONTROL_PLATFORM_QUERY_APP_SECRET",
      configDefaults: { queryTimeoutMs: 15000 },
      envIntDefaults: { CONTROL_PLATFORM_TIMEOUT_MS: "queryTimeoutMs" },
    },
  });

  const reasoning = createConfig({
    agentKey: "reasoning",
    envPath: path.resolve(__dirname, "..", ".env"),
    defaults: {
      agentId: "gateway-control-platform",
      agentName: "推理适配器",
      agentVersion: gateway.agentVersion,
      appKeyEnv: "CONTROL_PLATFORM_REASONING_APP_KEY",
      appSecretEnv: "CONTROL_PLATFORM_REASONING_APP_SECRET",
      configDefaults: { reasoningTimeoutMs: 180000 },
      envIntDefaults: { CONTROL_PLATFORM_REASONING_TIMEOUT_MS: "reasoningTimeoutMs" },
    },
  });

  // EXECUTION_AGENT_KEY 环境变量是 gateway，会被 createConfig 读成 gateway；
  // 适配器远程配置需要各自的 scope key。
  query.agentKey = "query";
  reasoning.agentKey = "reasoning";

  return { gateway, query, reasoning };
}

module.exports = { buildConfigs };
