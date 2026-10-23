"use strict";

const config = require("../config");
const { log, signedGet } = require("./http-client");

/** DB 配置键 → config 属性映射（仅非空值覆盖 env） */
const KEY_TO_PROP = {
  agent_name: "agentName",
  ws_url: "wsUrl",
  agent_id: "agentId",
  query_timeout_ms: "queryTimeoutMs",
  reasoning_timeout_ms: "reasoningTimeoutMs",
  log_level: "logLevel",
};

async function applyRemoteConfig() {
  const payload = await signedGet("/external/agent/config", "agent.config", {});
  const remote = (payload && payload.config) || {};
  const applied = [];
  for (const [key, prop] of Object.entries(KEY_TO_PROP)) {
    const value = remote[key];
    if (value === undefined || value === null || value === "") continue;
    if (String(config[prop]) === String(value)) continue;
    config[prop] = key.endsWith("_ms") ? Number(value) : value;
    applied.push(key);
  }
  config.configVersion = (payload && payload.version) || 0;
  log("info", "remote_config_applied", {
    version: config.configVersion,
    keys: applied,
    agentId: config.agentId,
    wsUrl: config.wsUrl,
  });
}

/** 启动即拉一次；失败用 env 值继续，每 60s 重试直到首次成功（只成功一次即停） */
function applyRemoteConfigWithRetry() {
  const timer = setInterval(async () => {
    try {
      await applyRemoteConfig();
      clearInterval(timer);
    } catch (e) {
      log("warn", "remote_config_retry_failed", { message: e.message });
    }
  }, 60_000);
  timer.unref();
  return applyRemoteConfig().catch((e) => {
    log("warn", "remote_config_failed", { message: e.message });
  });
}

module.exports = { applyRemoteConfig, applyRemoteConfigWithRetry };
