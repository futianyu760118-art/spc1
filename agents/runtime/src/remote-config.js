"use strict";

function createRemoteConfig({ config, configMap, http, log }) {
  async function applyRemoteConfig() {
    const payload = await http.signedGet(
      "/external/agent/config",
      "agent.config",
      { agent: config.agentKey },
      { timeoutMs: 5000 },
    );
    const remote = (payload && payload.config) || {};
    const applied = [];
    for (const [key, prop] of Object.entries(configMap)) {
      const value = remote[key];
      if (value === undefined || value === null || value === "") continue;
      if (String(config[prop]) === String(value)) continue;
      config[prop] = key.endsWith("_ms") ? Number(value) : value;
      applied.push(key);
    }
    config.configVersion = (payload && payload.version) || 0;
    log("info", "remote_config_applied", {
      agentKey: config.agentKey,
      version: config.configVersion,
      keys: applied,
      agentId: config.agentId,
      wsUrl: config.wsUrl,
    });
  }

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
    return applyRemoteConfig()
      .then(() => clearInterval(timer))
      .catch((e) => {
        log("warn", "remote_config_failed", { message: e.message });
      });
  }

  return { applyRemoteConfig, applyRemoteConfigWithRetry };
}

module.exports = { createRemoteConfig };
