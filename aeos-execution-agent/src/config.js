"use strict";

const fs = require("node:fs");
const path = require("node:path");

function fromEnv(fileVars, name, fallback) {
  const value = process.env[name] ?? fileVars[name];
  if (value === undefined || value === "") {
    if (fallback !== undefined) return fallback;
    throw new Error(`缺少必填配置 ${name}（参见 .env.example）`);
  }
  return value;
}

function toInt(fileVars, name, fallback) {
  const parsed = Number.parseInt(process.env[name] ?? fileVars[name] ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function loadEnvFile() {
  const envPath = path.resolve(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) return {};
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

function readAgentVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.resolve(__dirname, "..", "package.json"), "utf8")).version;
  } catch {
    return "0.0.0";
  }
}

const fileVars = loadEnvFile();

const config = {
  wsUrl: fromEnv(fileVars, "EXECUTION_WS_URL", "ws://127.0.0.1:8788/execution-agent"),
  token: fromEnv(fileVars, "EXECUTION_PLANE_TOKEN"),
  agentId: fromEnv(fileVars, "EXECUTION_AGENT_ID", "spc-execution-agent"),
  agentName: fromEnv(fileVars, "AGENT_NAME", "aeos-execution-agent"),
  agentVersion: fromEnv(fileVars, "AGENT_VERSION", readAgentVersion()),
  sourceSystem: process.env.EXECUTION_SOURCE_SYSTEM ?? fileVars.EXECUTION_SOURCE_SYSTEM ?? "",
  platformBaseUrl: fromEnv(fileVars, "CONTROL_PLATFORM_BASE_URL").replace(/\/+$/, ""),
  appKey: fromEnv(fileVars, "CONTROL_PLATFORM_APP_KEY"),
  appSecret: fromEnv(fileVars, "CONTROL_PLATFORM_APP_SECRET"),
  queryTimeoutMs: toInt(fileVars, "CONTROL_PLATFORM_TIMEOUT_MS", 15000),
  reasoningTimeoutMs: toInt(fileVars, "CONTROL_PLATFORM_REASONING_TIMEOUT_MS", 180000),
  healthCheckPort: toInt(fileVars, "HEALTH_CHECK_PORT", 8790),
  logLevel: fromEnv(fileVars, "LOG_LEVEL", "info"),
};

module.exports = config;
