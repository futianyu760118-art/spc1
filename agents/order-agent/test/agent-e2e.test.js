"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { startHub } = require("../../runtime/test/helpers/mock-hub");
const { startStubPlatform, spawnAgent, waitUntil, stopAgent } = require("../../runtime/test/helpers/agent-e2e");

test("order agent registers write capability and completes a schedule update", async () => {
  const hub = startHub();
  const platform = startStubPlatform({
    orderData: { order_no: "O-1", fields: { shipping_plan: "2026-11-01" }, updated_at: "2026-10-20T00:00:00" },
  });
  const hubPort = await hub.ready;
  const platformPort = await platform.ready;
  const agent = spawnAgent({
    entry: path.join(__dirname, "..", "src", "index.js"),
    env: {
      EXECUTION_AGENT_KEY: "order",
      EXECUTION_WS_URL: `ws://127.0.0.1:${hubPort}/execution-agent`,
      EXECUTION_PLANE_TOKEN: "test-token",
      EXECUTION_AGENT_ID: "runtime-control-platform-order",
      EXECUTION_AGENT_NAME: "公司中台订单智能体",
      CONTROL_PLATFORM_BASE_URL: `http://127.0.0.1:${platformPort}/api/v1`,
      CONTROL_PLATFORM_ORDER_APP_KEY: "test-key",
      CONTROL_PLATFORM_ORDER_APP_SECRET: "test-secret",
      CONTROL_PLATFORM_TIMEOUT_MS: "30000",
      HEALTH_CHECK_PORT: "0",
      LOG_LEVEL: "error",
      AGENT_ADMIN_TOKEN: "test-admin",
    },
  });
  try {
    await waitUntil(() => hub.messages.some((m) => m.type === "register"));
    const register = hub.messages.find((m) => m.type === "register");
    assert.equal(register.agentId, "runtime-control-platform-order");
    assert.equal(register.capabilities.length, 1);
    assert.equal(register.capabilities[0].name, "update_control_platform_order");
    assert.equal(register.capabilities[0].readOnly, false);

    hub.send({
      type: "dispatch",
      runId: "o-1",
      capability: "update_control_platform_order",
      input: { order_no: "O-1", fields: { shipping_plan: "2026-11-01" } },
    });
    await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "o-1"));
    const complete = hub.messages.find((m) => m.type === "run_complete" && m.runId === "o-1");
    assert.equal(complete.result.order_no, "O-1");
    assert.equal(complete.result.fields.shipping_plan, "2026-11-01");
  } finally {
    await stopAgent(agent);
    await hub.close();
    await platform.close();
  }
});
