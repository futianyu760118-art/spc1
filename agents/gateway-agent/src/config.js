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
      configDefaults: {
        queryTimeoutMs: 15000,
        reasoningTimeoutMs: 180000,
        resolverTimeoutMs: 30000,
        // 看门狗：0 关闭对应检测项（自愈靠 Docker restart 策略拉起）
        watchdogRunMaxMs: 900000,
        watchdogSelfPingIntervalMs: 30000,
        watchdogSelfPingTimeoutMs: 5000,
        watchdogSelfPingMaxFailures: 3,
        watchdogLoopStallMs: 10000,
      },
      envIntDefaults: {
        GATEWAY_RESOLVER_TIMEOUT_MS: "resolverTimeoutMs",
        WATCHDOG_RUN_MAX_MS: "watchdogRunMaxMs",
        WATCHDOG_SELF_PING_INTERVAL_MS: "watchdogSelfPingIntervalMs",
        WATCHDOG_SELF_PING_TIMEOUT_MS: "watchdogSelfPingTimeoutMs",
        WATCHDOG_SELF_PING_MAX_FAILURES: "watchdogSelfPingMaxFailures",
        WATCHDOG_LOOP_STALL_MS: "watchdogLoopStallMs",
      },
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

  const orderWrite = createConfig({
    agentKey: "order-write",
    envPath: path.resolve(__dirname, "..", ".env"),
    defaults: {
      agentId: "gateway-control-platform",
      agentName: "订单写适配器",
      agentVersion: gateway.agentVersion,
      appKeyEnv: "CONTROL_PLATFORM_ORDER_APP_KEY",
      appSecretEnv: "CONTROL_PLATFORM_ORDER_APP_SECRET",
      configDefaults: { writeTimeoutMs: 30000 },
      envIntDefaults: { CONTROL_PLATFORM_ORDER_TIMEOUT_MS: "writeTimeoutMs" },
    },
  });

  // EXECUTION_AGENT_KEY 环境变量是 gateway，会被 createConfig 读成 gateway；
  // 适配器远程配置需要各自的 scope key。
  query.agentKey = "query";
  reasoning.agentKey = "reasoning";
  orderWrite.agentKey = "order";

  return { gateway, query, reasoning, orderWrite };
}

module.exports = { buildConfigs };
