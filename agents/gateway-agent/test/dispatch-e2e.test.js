"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");
const path = require("node:path");
const { startHub } = require("../../runtime/test/helpers/mock-hub");
const {
  startStubPlatform,
  spawnAgent,
  waitUntil,
  stopAgent,
} = require("../../runtime/test/helpers/agent-e2e");

const ENTRY = path.resolve(__dirname, "../src/index.js");

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function gatewayEnv(hubPort, stubPort, adminPort = 0) {
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
    CONTROL_PLATFORM_ORDER_APP_KEY: "oak",
    CONTROL_PLATFORM_ORDER_APP_SECRET: "osk",
    GATEWAY_INTERNAL_TOKEN: "gw-token",
    AGENT_ADMIN_TOKEN: "admin-token",
    HEALTH_CHECK_PORT: String(adminPort),
    LOG_LEVEL: "error",
  };
}

test("gateway dispatches query and returns run_complete with caller/trace", async () => {
  const hub = startHub();
  const stub = startStubPlatform({ queryData: { ok: true, duration_ms: 20359.1 } });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });

    await waitUntil(() => hub.messages.some((message) => message.type === "register"));
    const register = hub.messages.find((message) => message.type === "register");
    assert.equal(register.agentId, "gateway-control-platform");
    assert.deepEqual(
      register.capabilities.map((capability) => capability.name).sort(),
      ["query_control_platform", "reason_control_platform", "write_control_platform"],
    );
    const writeCapability = register.capabilities.find(
      (capability) => capability.name === "write_control_platform",
    );
    assert.deepEqual(
      writeCapability.operations.map((operation) => operation.name),
      [
        "order.update_note",
        "order.update_status",
        "order.update_delivery_date",
      ],
    );

    hub.send({
      type: "dispatch",
      runId: "exec-run-e2e-1",
      capability: "query_control_platform",
      input: { path: "/external/orders/list", params: {} },
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
    assert.equal(complete.result.ok, true);
    assert.equal(complete.result.duration_ms, 20359);
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
    assert.equal(failed.error.code, "AGENT_NOT_FOUND");
    assert.match(failed.error.message, /AGENT_NOT_FOUND/);
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("returns handled_by and echoes request_id for reasoning runs", async () => {
  const hub = startHub();
  const stub = startStubPlatform({
    reasoningData: {
      task_id: "exec-run-e2e-r1",
      task_type: "order_delivery_analysis",
      status: "succeeded",
      summary: "存在交付风险",
      conclusions: [],
      llm: { called: true, provider: "openai", model: "deepseek-flash", latency_ms: 10 },
      request_id: null,
      usage: { modelId: "deepseek-flash", tokensIn: 1, cachedTokens: 0, tokensOut: 1 },
      duration_ms: 1234.6,
    },
  });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-e2e-r1",
      capability: "reason_control_platform",
      input: {
        prompt: "分析订单交付风险",
        task_type: "order_delivery_analysis",
        context: { businessObjectRef: "business://order/O-1" },
      },
      traceId: "trace-e2e-r1",
      request_id: "dispatch-req-1",
      caller: {
        systemId: "aeos-hub",
        agentId: "AG-000001",
        userId: "10086",
        taskId: "AT-E2E-R1",
        traceId: "trace-e2e-r1",
      },
    });

    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_complete" && message.runId === "exec-run-e2e-r1"),
    );
    const complete = hub.messages.find(
      (message) => message.type === "run_complete" && message.runId === "exec-run-e2e-r1",
    );
    assert.equal(complete.result.request_id, "dispatch-req-1");
    assert.deepEqual(complete.result.handled_by, {
      agentId: "spc-agent-order-risk",
      agentName: "订单风险分析 Agent",
      role: "order_risk",
      model: "deepseek-flash",
    });
    assert.equal(complete.result.duration_ms, 1235);
    assert.deepEqual(complete.usage, {
      modelId: "deepseek-flash",
      tokensIn: 1,
      cachedTokens: 0,
      tokensOut: 1,
    });

    const reasoningRequest = stub.requests.find(
      (request) => request.method === "POST" && request.path === "/external/reasoning/analyze",
    );
    assert.ok(reasoningRequest);
    assert.equal(reasoningRequest.body.request_id, "dispatch-req-1");
    assert.equal(reasoningRequest.body.task_type, "order_delivery_analysis");
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("returns AGENT_BUSY when a second dispatch arrives during an active run", async () => {
  const hub = startHub();
  const stub = startStubPlatform({ queryData: { ok: true }, queryDelayMs: 300 });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-busy-1",
      capability: "query_control_platform",
      input: { path: "/external/orders/list", params: {} },
      traceId: "trace-busy-1",
    });
    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_update" && message.runId === "exec-run-busy-1"),
    );

    hub.send({
      type: "dispatch",
      runId: "exec-run-busy-2",
      capability: "query_control_platform",
      input: { path: "/external/orders/list", params: {} },
    });
    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_failed" && message.runId === "exec-run-busy-2"),
    );
    const failed = hub.messages.find(
      (message) => message.type === "run_failed" && message.runId === "exec-run-busy-2",
    );
    assert.equal(failed.error.code, "AGENT_BUSY");

    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_complete" && message.runId === "exec-run-busy-1"),
    );
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("returns TARGET_AGENT_UNAVAILABLE for an unknown target_agent_ref", async () => {
  const hub = startHub();
  const stub = startStubPlatform();
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-target-missing",
      capability: "reason_control_platform",
      input: {
        prompt: "分析订单交付风险",
        task_type: "order_delivery_analysis",
        context: { businessObjectRef: "business://order/O-1" },
      },
      request_id: "dispatch-req-target",
      target_agent_ref: "spc-agent-missing",
      caller: { systemId: "aeos-hub", agentId: "AG-000001" },
    });

    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_failed" && message.runId === "exec-run-target-missing"),
    );
    const failed = hub.messages.find(
      (message) => message.type === "run_failed" && message.runId === "exec-run-target-missing",
    );
    assert.equal(failed.error.code, "TARGET_AGENT_UNAVAILABLE");
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("returns write result with handled_by and echoed request_id", async () => {
  const hub = startHub();
  const stub = startStubPlatform({
    writeData: {
      ok: true,
      operation: "order.update_note",
      target: { orderNo: "HJY-WRITE-1" },
      before: { remark: "" },
      after: { remark: "new note" },
      appliedAt: "2026-10-28T13:00:00+08:00",
      idempotent_replay: false,
    },
  });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-write-1",
      capability: "write_control_platform",
      input: {
        operation: "order.update_note",
        orderNo: "HJY-WRITE-1",
        changes: { remark: "new note" },
        idempotencyKey: "write-idem-1",
      },
      request_id: "dispatch-write-1",
      caller: { systemId: "aeos-hub", agentId: "AG-000001", userId: "m01:user:1" },
    });

    await waitUntil(() =>
      hub.messages.some((message) => message.type === "run_complete" && message.runId === "exec-run-write-1"),
    );
    const complete = hub.messages.find(
      (message) => message.type === "run_complete" && message.runId === "exec-run-write-1",
    );
    assert.equal(complete.result.request_id, "dispatch-write-1");
    assert.equal(complete.result.appliedAt, "2026-10-28T13:00:00+08:00");
    assert.equal(complete.result.idempotent_replay, false);
    assert.deepEqual(complete.result.handled_by, {
      agentId: "spc-agent-order-write",
      agentName: "订单写操作 Agent",
      role: "order_write",
    });

    const writeRequest = stub.requests.find(
      (request) => request.method === "PUT" && request.path.endsWith("/write"),
    );
    assert.ok(writeRequest);
    assert.equal(writeRequest.body.operation, "order.update_note");
    assert.equal(writeRequest.body.idempotencyKey, "write-idem-1");
    assert.equal(writeRequest.body.request_id, "dispatch-write-1");
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("admin local run executes write capability for the assistant", async () => {
  const hub = startHub();
  const stub = startStubPlatform({
    writeData: {
      ok: true,
      operation: "order.update_schedule_fields",
      target: { orderNo: "O-9" },
      before: { promised_date: null },
      after: { promised_date: "2026-11-20" },
      appliedAt: "2026-10-28T16:00:00+08:00",
      idempotent_replay: false,
    },
  });
  let agent;
  try {
    const [hubPort, stubPort, adminPort] = await Promise.all([
      hub.ready, stub.ready, freePort(),
    ]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort, adminPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));
    await waitUntil(async () => {
      try {
        const res = await fetch(`http://127.0.0.1:${adminPort}/healthz`);
        return res.status === 200 || res.status === 503;
      } catch {
        return false;
      }
    });

    const response = await fetch(`http://127.0.0.1:${adminPort}/admin/run`, {
      method: "POST",
      headers: { "x-admin-token": "admin-token", "Content-Type": "application/json" },
      body: JSON.stringify({
        capability: "write_control_platform",
        input: {
          operation: "order.update_schedule_fields",
          orderNo: "O-9",
          changes: { fields: { promised_date: "2026-11-20" } },
          idempotencyKey: "assistant-idem-1",
        },
        actorToken: "assistant-actor-token",
        requestId: "assistant-req-1",
      }),
    });
    const payload = await response.json();
    assert.equal(response.status, 200, `admin/run 失败：${JSON.stringify(payload)}`);
    assert.equal(payload.ok, true);
    assert.equal(payload.result.operation, "order.update_schedule_fields");
    assert.deepEqual(payload.result.after, { promised_date: "2026-11-20" });

    const writeRequest = stub.requests.find(
      (request) => request.method === "PUT" && request.path.endsWith("/write"),
    );
    assert.ok(writeRequest);
    assert.equal(writeRequest.body.operation, "order.update_schedule_fields");
    assert.deepEqual(writeRequest.body.changes, { fields: { promised_date: "2026-11-20" } });
    assert.equal(writeRequest.body.idempotencyKey, "assistant-idem-1");
    assert.equal(writeRequest.body.request_id, "assistant-req-1");
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("returns CAPABILITY_UNSUPPORTED for an unknown write operation", async () => {
  const hub = startHub();
  const stub = startStubPlatform();
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-write-unknown",
      capability: "write_control_platform",
      input: {
        operation: "order.delete",
        orderNo: "HJY-WRITE-1",
        changes: {},
        idempotencyKey: "write-idem-unknown",
      },
      request_id: "dispatch-write-unknown",
      caller: { systemId: "aeos-hub", agentId: "AG-000001" },
    });

    await waitUntil(() =>
      hub.messages.some(
        (message) => message.type === "run_failed" && message.runId === "exec-run-write-unknown",
      ),
    );
    const failed = hub.messages.find(
      (message) => message.type === "run_failed" && message.runId === "exec-run-write-unknown",
    );
    assert.equal(failed.error.code, "CAPABILITY_UNSUPPORTED");
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});

test("routes delivery date writes and returns before/after", async () => {
  const hub = startHub();
  const stub = startStubPlatform({
    writeData: {
      ok: true,
      operation: "order.update_delivery_date",
      target: { orderNo: "HJY-WRITE-2" },
      before: { deliveryDate: null },
      after: { deliveryDate: "2026-11-10" },
      appliedAt: "2026-10-28T14:10:00+08:00",
      idempotent_replay: false,
    },
  });
  let agent;
  try {
    const [hubPort, stubPort] = await Promise.all([hub.ready, stub.ready]);
    agent = spawnAgent({ entry: ENTRY, env: gatewayEnv(hubPort, stubPort) });
    await waitUntil(() => hub.messages.some((message) => message.type === "register"));

    hub.send({
      type: "dispatch",
      runId: "exec-run-write-delivery",
      capability: "write_control_platform",
      input: {
        operation: "order.update_delivery_date",
        orderNo: "HJY-WRITE-2",
        changes: { deliveryDate: "2026-11-10" },
        idempotencyKey: "write-delivery-idem",
      },
      request_id: "dispatch-write-delivery",
      caller: { systemId: "aeos-hub", agentId: "AG-000001" },
    });

    await waitUntil(() =>
      hub.messages.some(
        (message) => message.type === "run_complete" && message.runId === "exec-run-write-delivery",
      ),
    );
    const complete = hub.messages.find(
      (message) => message.type === "run_complete" && message.runId === "exec-run-write-delivery",
    );
    assert.equal(complete.result.request_id, "dispatch-write-delivery");
    assert.deepEqual(complete.result.before, { deliveryDate: null });
    assert.deepEqual(complete.result.after, { deliveryDate: "2026-11-10" });
    assert.deepEqual(complete.result.handled_by, {
      agentId: "spc-agent-order-write",
      agentName: "订单写操作 Agent",
      role: "order_write",
    });

    const writeRequest = stub.requests.find(
      (request) => request.method === "PUT" && request.path.endsWith("/write"),
    );
    assert.ok(writeRequest);
    assert.equal(writeRequest.body.operation, "order.update_delivery_date");
    assert.deepEqual(writeRequest.body.changes, { deliveryDate: "2026-11-10" });
  } finally {
    if (agent) await stopAgent(agent);
    await hub.close();
    await stub.close();
  }
});
