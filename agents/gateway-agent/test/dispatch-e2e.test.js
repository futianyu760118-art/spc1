"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { startHub } = require("../../runtime/test/helpers/mock-hub");
const {
  startStubPlatform,
  spawnAgent,
  waitUntil,
  stopAgent,
} = require("../../runtime/test/helpers/agent-e2e");

const ENTRY = path.resolve(__dirname, "../src/index.js");

function gatewayEnv(hubPort, stubPort) {
  return {
    EXECUTION_AGENT_KEY: "gateway",
    EXECUTION_WS_URL: `ws://127.0.0.1:${hubPort}/execution-agent`,
    EXECUTION_PLANE_TOKEN: "",
    EXECUTION_AGENT_ID: "gateway-control-platform",
    EXECUTION_AGENT_NAME: "测试系统网关",
    EXECUTION_SYSTEM_ID: "control-platform",
    EXECUTION_SYSTEM_TOKEN: "system-token",
    EXECUTION_SOURCE_SYSTEM: "control-platform",
    CONTROL_PLATFORM_BASE_URL: `http://127.0.0.1:${stubPort}/api/v1`,
    BACKEND_INTERNAL_BASE_URL: `http://127.0.0.1:${stubPort}`,
    CONTROL_PLATFORM_QUERY_APP_KEY: "ak",
    CONTROL_PLATFORM_QUERY_APP_SECRET: "sk",
    CONTROL_PLATFORM_REASONING_APP_KEY: "rak",
    CONTROL_PLATFORM_REASONING_APP_SECRET: "rsk",
    GATEWAY_INTERNAL_TOKEN: "gw-token",
    AGENT_ADMIN_TOKEN: "admin-token",
    HEALTH_CHECK_PORT: "0",
    LOG_LEVEL: "error",
  };
}

test("gateway dispatches query and returns run_complete with caller/trace", async () => {
  const hub = startHub();
  const stub = startStubPlatform({ queryData: { ok: true } });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });

    await waitUntil(() => hub.messages.some((message) => message.type === "register"));
    const register = hub.messages.find((message) => message.type === "register");
    assert.equal(register.agentId, "gateway-control-platform");
    assert.deepEqual(
      register.capabilities.map((capability) => capability.name).sort(),
      ["query_control_platform", "reason_control_platform"],
    );

    hub.send({
      type: "dispatch",
      runId: "exec-run-e2e-1",
      capability: "query_control_platform",
      input: { path: "/common/ping", params: {} },
      traceId: "trace-e2e-1",
      caller: {
        systemId: "aeos-hub",
        agentId: "AG-000001",
        userId: "10086",
        taskId: "AT-E2E-1",
        traceId: "trace-e2e-1",
      },
    });

    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_complete" && message.runId === "exec-run-e2e-1"),
    );
    const complete = hub.messages.find(
      (message) => message.type === "run_complete" && message.runId === "exec-run-e2e-1",
    );
    assert.deepEqual(complete.result, { ok: true });
    assert.equal(complete.traceId, "trace-e2e-1");
    assert.equal(complete.taskId, "AT-E2E-1");

    const update = hub.messages.find(
      (message) => message.type === "run_update" && message.runId === "exec-run-e2e-1",
    );
    assert.equal(update.state, "running");

    const events = hub.messages.filter(
      (message) => message.type === "run_event" && message.runId === "exec-run-e2e-1",
    );
    assert.ok(events.length >= 2);
    assert.ok(events.every((event) => event.traceId === "trace-e2e-1"));
    assert.ok(events.every((event) => event.taskId === "AT-E2E-1"));
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("gateway returns run_failed when caller cannot be resolved", async () => {
  const hub = startHub();
  const stub = startStubPlatform();
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-e2e-reject",
      capability: "query_control_platform",
      input: { path: "/common/ping", params: {} },
      traceId: "trace-e2e-reject",
      caller: { systemId: "aeos-hub", agentId: "AG-REJECT" },
    });

    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_failed" && message.runId === "exec-run-e2e-reject"),
    );
    const failed = hub.messages.find(
      (message) => message.type === "run_failed" && message.runId === "exec-run-e2e-reject",
    );
    assert.equal(failed.error.code, "INVALID_ARGUMENT");
    assert.match(failed.error.message, /AGENT_NOT_FOUND/);
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});
