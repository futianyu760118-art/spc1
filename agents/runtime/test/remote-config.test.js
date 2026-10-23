"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createRemoteConfig } = require("../src/remote-config");

function createConfig() {
  return {
    agentKey: "query",
    agentName: "本地名",
    wsUrl: "ws://local",
    queryTimeoutMs: 15000,
    logLevel: "info",
    configVersion: 0,
  };
}

const CONFIG_MAP = {
  agent_name: "agentName",
  ws_url: "wsUrl",
  query_timeout_ms: "queryTimeoutMs",
  log_level: "logLevel",
};

test("applyRemoteConfig updates config and records the remote version", async () => {
  const calls = [];
  const config = createConfig();
  const http = {
    signedGet: async (...args) => {
      calls.push(args);
      return {
        version: 7,
        config: {
          agent_name: "远程名",
          ws_url: "ws://remote",
          query_timeout_ms: "21000",
          log_level: "debug",
        },
      };
    },
  };
  const remote = createRemoteConfig({ config, configMap: CONFIG_MAP, http, log: () => {} });

  await remote.applyRemoteConfig();

  assert.equal(config.agentName, "远程名");
  assert.equal(config.wsUrl, "ws://remote");
  assert.equal(config.queryTimeoutMs, 21000);
  assert.equal(config.logLevel, "debug");
  assert.equal(config.configVersion, 7);
  assert.equal(calls[0][0], "/external/agent/config");
  assert.equal(calls[0][1], "agent.config");
  assert.deepEqual(calls[0][2], { agent: "query" });
});

test("applyRemoteConfigWithRetry clears the retry timer after the initial success", async () => {
  const originalSetInterval = global.setInterval;
  const originalClearInterval = global.clearInterval;
  const fakeTimer = { unref() {} };
  const cleared = [];
  global.setInterval = () => fakeTimer;
  global.clearInterval = (timer) => cleared.push(timer);
  try {
    const http = { signedGet: async () => ({ version: 3, config: {} }) };
    const remote = createRemoteConfig({
      config: createConfig(),
      configMap: CONFIG_MAP,
      http,
      log: () => {},
    });

    await remote.applyRemoteConfigWithRetry();

    assert.deepEqual(cleared, [fakeTimer]);
  } finally {
    global.setInterval = originalSetInterval;
    global.clearInterval = originalClearInterval;
  }
});
