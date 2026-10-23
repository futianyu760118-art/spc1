"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { startHub } = require("../../runtime/test/helpers/mock-hub");
const { startStubPlatform, spawnAgent, waitUntil, stopAgent } = require("../../runtime/test/helpers/agent-e2e");

const ENTRY = path.resolve(__dirname, "../src/index.js");

test("query agent registers and completes a whitelisted query end to end", async () => {
  const hub = startHub();
  const stub = startStubPlatform({ queryData: { items: [{ id: 1 }] } });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({
      entry: ENTRY,
      env: {
        EXECUTION_AGENT_KEY: "query",
        EXECUTION_WS_URL: `ws://127.0.0.1:${hubPort}/execution-agent`,
        EXECUTION_PLANE_TOKEN: "test-token",
        EXECUTION_AGENT_ID: "runtime-control-platform-query",
        EXECUTION_AGENT_NAME: "公司中台查询智能体",
        CONTROL_PLATFORM_BASE_URL: `http://127.0.0.1:${stubPort}/api/v1`,
        CONTROL_PLATFORM_QUERY_APP_KEY: "test-key",
        CONTROL_PLATFORM_QUERY_APP_SECRET: "test-secret",
        HEALTH_CHECK_PORT: "0",
        LOG_LEVEL: "error",
        AGENT_ADMIN_TOKEN: "test-admin",
      },
    });

    await waitUntil(() => hub.messages.some((message) => message.type === "register"));
    const register = hub.messages.find((message) => message.type === "register");
    assert.equal(register.agentId, "runtime-control-platform-query");
    assert.equal(register.capabilities.length, 1);
    const capability = register.capabilities[0];
    assert.equal(capability.name, "query_control_platform");
    assert.equal(capability.readOnly, true);
    assert.equal(capability.constraints.readOnly, true);

    hub.send({
      type: "dispatch",
      runId: "q1",
      capability: "query_control_platform",
      input: { path: "/external/orders/list", params: { page: 1 } },
    });

    await waitUntil(() => hub.messages.some((message) => message.type === "run_complete" && message.runId === "q1"));
    const complete = hub.messages.find((message) => message.type === "run_complete" && message.runId === "q1");
    assert.deepEqual(complete.result, { items: [{ id: 1 }] });
    assert.ok(
      stub.requests.some((request) => request.method === "GET" && request.path === "/external/agent/config"),
    );
    assert.ok(
      stub.requests.some((request) => request.method === "GET" && request.path === "/external/orders/list"),
    );
  } catch (e) {
    if (agent) e.message += `\n--- agent logs ---\n${agent.logs.join("")}`;
    throw e;
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});
