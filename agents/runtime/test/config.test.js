"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { createConfig } = require("../src/config");

const ENV_NAMES = [
  "EXECUTION_AGENT_KEY",
  "EXECUTION_AGENT_ID",
  "EXECUTION_AGENT_NAME",
  "EXECUTION_WS_URL",
  "EXECUTION_PLANE_TOKEN",
  "EXECUTION_SOURCE_SYSTEM",
  "AGENT_VERSION",
  "CONTROL_PLATFORM_BASE_URL",
  "CONTROL_PLATFORM_QUERY_APP_KEY",
  "CONTROL_PLATFORM_QUERY_APP_SECRET",
  "CONTROL_PLATFORM_TIMEOUT_MS",
  "HEALTH_CHECK_PORT",
  "LOG_LEVEL",
  "AGENT_ADMIN_TOKEN",
  "BACKEND_INTERNAL_BASE_URL",
  "GATEWAY_INTERNAL_TOKEN",
  "AEOS_HUB_BASE",
  "AEOS_SYSTEM_ID",
  "AEOS_SYSTEM_TOKEN",
];

function withEnv(values, fn) {
  const saved = Object.fromEntries(ENV_NAMES.map((name) => [name, process.env[name]]));
  for (const name of ENV_NAMES) delete process.env[name];
  for (const [name, value] of Object.entries(values)) process.env[name] = value;
  try {
    return fn();
  } finally {
    for (const name of ENV_NAMES) {
      if (saved[name] === undefined) delete process.env[name];
      else process.env[name] = saved[name];
    }
  }
}

const QUERY_DEFAULTS = {
  agentId: "runtime-control-platform-query",
  agentName: "查询智能体",
  agentVersion: "1.0.0",
  appKeyEnv: "CONTROL_PLATFORM_QUERY_APP_KEY",
  appSecretEnv: "CONTROL_PLATFORM_QUERY_APP_SECRET",
  configDefaults: { queryTimeoutMs: 15000 },
  envIntDefaults: { CONTROL_PLATFORM_TIMEOUT_MS: "queryTimeoutMs" },
};

test("createConfig reads agent-specific keys and applies env int defaults", () => {
  withEnv({
    EXECUTION_AGENT_KEY: "query",
    EXECUTION_PLANE_TOKEN: "token",
    CONTROL_PLATFORM_BASE_URL: "http://platform/api/v1/",
    CONTROL_PLATFORM_QUERY_APP_KEY: "ak",
    CONTROL_PLATFORM_QUERY_APP_SECRET: "sk",
    CONTROL_PLATFORM_TIMEOUT_MS: "21000",
  }, () => {
    const cfg = createConfig({
      agentKey: "query",
      envPath: "",
      defaults: QUERY_DEFAULTS,
    });

    assert.equal(cfg.agentKey, "query");
    assert.equal(cfg.platformBaseUrl, "http://platform/api/v1");
    assert.equal(cfg.queryTimeoutMs, 21000);
    assert.equal(cfg.appKey, "ak");
    assert.equal(cfg.appSecret, "sk");
  });
});

test("createConfig reads gateway internal and hub connection settings", () => {
  withEnv({
    EXECUTION_AGENT_KEY: "query",
    EXECUTION_PLANE_TOKEN: "token",
    CONTROL_PLATFORM_BASE_URL: "http://platform/api/v1",
    CONTROL_PLATFORM_QUERY_APP_KEY: "ak",
    CONTROL_PLATFORM_QUERY_APP_SECRET: "sk",
    BACKEND_INTERNAL_BASE_URL: " http://backend:8000 ",
    GATEWAY_INTERNAL_TOKEN: "gw-token",
    AEOS_HUB_BASE: " https://hub.example.com ",
    AEOS_SYSTEM_ID: "control-platform",
    AEOS_SYSTEM_TOKEN: "system-token",
  }, () => {
    const cfg = createConfig({ agentKey: "query", envPath: "", defaults: QUERY_DEFAULTS });

    assert.equal(cfg.backendInternalBaseUrl, "http://backend:8000");
    assert.equal(cfg.gatewayInternalToken, "gw-token");
    assert.equal(cfg.hubBaseUrl, "https://hub.example.com");
    assert.equal(cfg.hubSystemId, "control-platform");
    assert.equal(cfg.hubSystemToken, "system-token");
  });
});

test("createConfig throws when a required key is missing", () => {
  withEnv({ EXECUTION_AGENT_KEY: "query" }, () => {
    assert.throws(
      () => createConfig({ agentKey: "query", envPath: "", defaults: QUERY_DEFAULTS }),
      /缺少必填配置 EXECUTION_PLANE_TOKEN/,
    );
  });
});

test("createConfig allows empty legacy token when system token is configured", () => {
  withEnv({
    EXECUTION_AGENT_KEY: "query",
    EXECUTION_SYSTEM_ID: "control-platform",
    EXECUTION_SYSTEM_TOKEN: "system-token",
    CONTROL_PLATFORM_BASE_URL: "http://platform/api/v1",
    CONTROL_PLATFORM_QUERY_APP_KEY: "ak",
    CONTROL_PLATFORM_QUERY_APP_SECRET: "sk",
  }, () => {
    const config = createConfig({ agentKey: "query", envPath: "", defaults: QUERY_DEFAULTS });
    assert.equal(config.token, "");
    assert.equal(config.systemId, "control-platform");
    assert.equal(config.systemToken, "system-token");
  });
});

test("createConfig reads .env values and lets them override defaults", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "spc-agent-config-"));
  const envPath = path.join(dir, ".env");
  fs.writeFileSync(envPath, [
    "EXECUTION_AGENT_KEY=query",
    "EXECUTION_PLANE_TOKEN=file-token",
    "CONTROL_PLATFORM_BASE_URL=http://file-platform/api/v1/",
    "CONTROL_PLATFORM_QUERY_APP_KEY=file-ak",
    "CONTROL_PLATFORM_QUERY_APP_SECRET=file-sk",
    "CONTROL_PLATFORM_TIMEOUT_MS=18000",
    "EXECUTION_AGENT_NAME=文件智能体",
    "LOG_LEVEL=debug",
    "HEALTH_CHECK_PORT=9999",
  ].join("\n"));

  try {
    withEnv({}, () => {
      const cfg = createConfig({
        agentKey: "query",
        envPath,
        defaults: QUERY_DEFAULTS,
      });

      assert.equal(cfg.token, "file-token");
      assert.equal(cfg.agentName, "文件智能体");
      assert.equal(cfg.logLevel, "debug");
      assert.equal(cfg.healthCheckPort, 9999);
      assert.equal(cfg.queryTimeoutMs, 18000);
      assert.equal(cfg.platformBaseUrl, "http://file-platform/api/v1");
    });
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
