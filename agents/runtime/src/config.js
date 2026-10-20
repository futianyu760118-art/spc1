"use strict";

const fs = require("node:fs");

function loadEnvFile(envPath) {
  if (!envPath || !fs.existsSync(envPath)) return {};
  const vars = {};
  for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    vars[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1).trim();
  }
  return vars;
}

function createConfig({ agentKey, envPath, defaults = {} }) {
  const fileVars = loadEnvFile(envPath);
  const read = (name, fallback) => {
    const value = process.env[name] ?? fileVars[name];
    if (value === undefined || value === "") {
      if (fallback !== undefined) return fallback;
      throw new Error(`缺少必填配置 ${name}（参见 .env.example）`);
    }
    return value;
  };
  const toInt = (name, fallback) => {
    const parsed = Number.parseInt(process.env[name] ?? fileVars[name] ?? "", 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const config = {
    ...defaults.configDefaults,
    agentKey: read("EXECUTION_AGENT_KEY", agentKey),
    wsUrl: read("EXECUTION_WS_URL", defaults.wsUrl ?? "ws://127.0.0.1:8788/execution-agent"),
    token: read("EXECUTION_PLANE_TOKEN"),
    agentId: read("EXECUTION_AGENT_ID", defaults.agentId),
    agentName: read("EXECUTION_AGENT_NAME", defaults.agentName),
    agentVersion: read("AGENT_VERSION", defaults.agentVersion),
    sourceSystem: process.env.EXECUTION_SOURCE_SYSTEM ?? fileVars.EXECUTION_SOURCE_SYSTEM ?? "",
    platformBaseUrl: read("CONTROL_PLATFORM_BASE_URL").replace(/\/+$/, ""),
    appKey: read(defaults.appKeyEnv ?? "CONTROL_PLATFORM_APP_KEY"),
    appSecret: read(defaults.appSecretEnv ?? "CONTROL_PLATFORM_APP_SECRET"),
    healthCheckPort: toInt("HEALTH_CHECK_PORT", defaults.healthCheckPort ?? 8790),
    logLevel: read("LOG_LEVEL", "info"),
    adminToken: process.env.AGENT_ADMIN_TOKEN ?? fileVars.AGENT_ADMIN_TOKEN ?? "",
    systemId: process.env.EXECUTION_SYSTEM_ID ?? fileVars.EXECUTION_SYSTEM_ID ?? "",
    systemToken: process.env.EXECUTION_SYSTEM_TOKEN ?? fileVars.EXECUTION_SYSTEM_TOKEN ?? "",
    configVersion: 0,
  };

  for (const [envName, prop] of Object.entries(defaults.envIntDefaults || {})) {
    config[prop] = toInt(envName, config[prop]);
  }
  return config;
}

module.exports = { createConfig, loadEnvFile };
