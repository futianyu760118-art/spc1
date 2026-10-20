"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { startHub } = require("../../runtime/test/helpers/mock-hub");
const { startStubPlatform, spawnAgent, waitUntil, stopAgent } = require("../../runtime/test/helpers/agent-e2e");

const ENTRY = path.resolve(__dirname, "../src/index.js");

test("reasoning agent registers and lifts usage above the result end to end", async () => {
  const hub = startHub();
  const stub = startStubPlatform({
    reasoningData: {
      task_id: "r1",
      task_type: "order_delivery_analysis",
      status: "succeeded",
      summary: "ok",
      conclusions: [],
      usage: { total_tokens: 10 },
    },
  });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({
      entry: ENTRY,
      env: {
        EXECUTION_AGENT_KEY: "reasoning",
        EXECUTION_WS_URL: `ws://127.0.0.1:${hubPort}/execution-agent`,
        EXECUTION_PLANE_TOKEN: "test-token",
        EXECUTION_AGENT_ID: "runtime-control-platform-reasoning",
        EXECUTION_AGENT_NAME: "公司中台推理智能体",
        CONTROL_PLATFORM_BASE_URL: `http://127.0.0.1:${stubPort}/api/v1`,
        CONTROL_PLATFORM_REASONING_APP_KEY: "test-key",
        CONTROL_PLATFORM_REASONING_APP_SECRET: "test-secret",
        CONTROL_PLATFORM_REASONING_TIMEOUT_MS: "30000",
        HEALTH_CHECK_PORT: "0",
        LOG_LEVEL: "error",
        AGENT_ADMIN_TOKEN: "test-admin",
      },
    });

    await waitUntil(() => hub.messages.some((message) => message.type === "register"));
    const register = hub.messages.find((message) => message.type === "register");
    assert.equal(register.agentId, "runtime-control-platform-reasoning");
    assert.equal(register.capabilities.length, 1);
    const capability = register.capabilities[0];
    assert.equal(capability.name, "reason_control_platform");
    assert.equal(capability.readOnly, true);
    assert.equal(capability.constraints.requireEvidence, true);

    hub.send({
      type: "dispatch",
      runId: "r1",
      capability: "reason_control_platform",
      input: {
        prompt: "分析",
        task_type: "order_delivery_analysis",
        context: { businessObjectRef: "business://order/1" },
      },
    });

    await waitUntil(() => hub.messages.some((message) => message.type === "run_complete" && message.runId === "r1"));
    const complete = hub.messages.find((message) => message.type === "run_complete" && message.runId === "r1");
    assert.equal(complete.result.summary, "ok");
    assert.deepEqual(complete.usage, { total_tokens: 10 });
    assert.equal("usage" in complete.result, false);
  } catch (e) {
    if (agent) e.message += `\n--- agent logs ---\n${agent.logs.join("")}`;
    throw e;
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});
