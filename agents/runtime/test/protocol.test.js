"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { HubConnection } = require("../src/protocol");
const { startHub } = require("./helpers/mock-hub");

function createConfig(port, overrides = {}) {
  return {
    wsUrl: `ws://127.0.0.1:${port}/execution-agent`,
    token: "test-token",
    agentId: "runtime-control-platform-query",
    agentName: "查询智能体",
    agentVersion: "1.0.0",
    sourceSystem: "test",
    ...overrides,
  };
}

function waitUntil(predicate, timeoutMs = 3000) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(() => {
      if (predicate()) {
        clearInterval(timer);
        resolve();
      } else if (Date.now() - startedAt > timeoutMs) {
        clearInterval(timer);
        reject(new Error("waitUntil timeout"));
      }
    }, 20);
  });
}

function registerMessages(hub) {
  return hub.messages.filter((m) => m.type === "register");
}

test("registers with identity and capabilities, dispatches, reports completion and ignores duplicate dispatch", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const logs = [];
  let release;
  let dispatchedRun;
  const gate = new Promise((resolve) => { release = resolve; });
  const connection = new HubConnection({
    config: createConfig(port),
    log: (level, event) => logs.push({ level, event }),
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async (run) => {
        dispatchedRun = run;
        await gate;
        return { items: [1] };
      },
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => hub.messages.some((m) => m.type === "register"));
  const register = registerMessages(hub)[0];
  assert.equal(hub.tokens[0], "test-token");
  assert.deepEqual(
    {
      agentId: register.agentId,
      name: register.name,
      version: register.version,
      sourceSystem: register.sourceSystem,
      capabilities: register.capabilities.map((c) => c.name),
    },
    {
      agentId: "runtime-control-platform-query",
      name: "查询智能体",
      version: "1.0.0",
      sourceSystem: "test",
      capabilities: ["query_control_platform"],
    },
  );
  assert.equal(register.capabilities[0].version, "1.0.0");
  await waitUntil(() => connection.isRegistered());

  hub.send({
    type: "dispatch",
    runId: "run-1",
    capability: "query_control_platform",
    input: { path: "/external/orders/list" },
    traceId: "trace-1",
    caller: {
      systemId: "aeos-hub",
      agentId: "AG-000001",
      userId: " 10086 ",
      taskId: "AT-000123",
      traceId: "trace-1",
      token: "must-not-leak",
    },
  });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_update" && m.runId === "run-1"));

  const update = hub.messages.find((m) => m.type === "run_update" && m.runId === "run-1");
  const received = hub.messages.find((m) => m.type === "run_event" && m.event === "run_received");
  assert.equal(update.traceId, "trace-1");
  assert.equal(update.taskId, "AT-000123");
  assert.equal(received.traceId, "trace-1");
  assert.equal(received.taskId, "AT-000123");
  assert.deepEqual(dispatchedRun.caller, {
    systemId: "aeos-hub",
    agentId: "AG-000001",
    userId: "10086",
    taskId: "AT-000123",
    traceId: "trace-1",
  });
  assert.equal(dispatchedRun.traceId, "trace-1");
  assert.equal(dispatchedRun.taskId, "AT-000123");

  hub.send({ type: "dispatch", runId: "run-2", capability: "query_control_platform", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-2"));
  const busy = hub.messages.find((m) => m.type === "run_failed" && m.runId === "run-2");
  assert.equal(busy.error.code, "AGENT_BUSY");
  assert.equal(busy.error.message, "agent busy");

  release();
  await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-1"));
  const complete = hub.messages.find((m) => m.type === "run_complete" && m.runId === "run-1");
  assert.deepEqual(complete.result, { items: [1] });
  assert.equal(complete.traceId, "trace-1");
  assert.equal(complete.taskId, "AT-000123");
  assert.equal(logs.some((l) => l.event === "run_started"), true);
});

test("tolerates a missing caller and falls back to runId for trace and top-level events", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  let dispatchedRun;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async (run) => {
        dispatchedRun = run;
        return { ok: true };
      },
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({ type: "dispatch", runId: "run-null", capability: "query_control_platform", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-null"));

  assert.equal(dispatchedRun.caller, null);
  assert.equal(dispatchedRun.traceId, "run-null");
  assert.equal(dispatchedRun.taskId, null);
  const events = hub.messages.filter(
    (m) => (m.type === "run_update" || m.type === "run_event" || m.type === "run_complete") && m.runId === "run-null",
  );
  assert.ok(events.length >= 3);
  for (const message of events) {
    assert.equal(message.traceId, "run-null");
    assert.equal("taskId" in message, false);
  }
});

test("local runs do not occupy the hub run slot", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => ({ ok: true }),
      onRecall: () => {},
    },
  });
  const localRun = { runId: "local-1", controller: new AbortController() };
  connection.localRuns.set("local-1", localRun);
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({ type: "dispatch", runId: "run-hub", capability: "query_control_platform", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-hub"));

  assert.equal(hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-hub"), false);
  assert.equal(connection.localRuns.has("local-1"), true);
  assert.equal(localRun.recalled, undefined);
});

test("abortActive tears down the hub run and every local run", () => {
  let recalled = [];
  const connection = new HubConnection({
    config: createConfig(1),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => null,
      onRecall: (runId) => recalled.push(runId),
    },
  });
  const hubRun = { runId: "hub-1", recalled: false, controller: new AbortController() };
  const localRun = { runId: "local-1", recalled: false, controller: new AbortController() };
  connection.hubRun = hubRun;
  connection.localRuns.set("local-1", localRun);

  connection.abortActive("shutdown");

  assert.equal(hubRun.recalled, true);
  assert.equal(localRun.recalled, true);
  assert.equal(hubRun.controller.signal.aborted, true);
  assert.equal(localRun.controller.signal.aborted, true);
  assert.deepEqual(recalled.sort(), ["hub-1", "local-1"]);
});

test("recall aborts the active run and does not report completion", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  let recalled = 0;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: (run) => new Promise((resolve, reject) => {
        run.controller.signal.addEventListener("abort", () => {
          const err = new Error("aborted");
          err.code = "ABORTED";
          reject(err);
        });
      }),
      onRecall: () => { recalled += 1; },
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({ type: "dispatch", runId: "run-r", capability: "query_control_platform", input: {} });
  await waitUntil(() => connection.hubRun);
  hub.send({ type: "recall", runId: "run-r" });
  await waitUntil(() => recalled === 1);
  await new Promise((resolve) => setTimeout(resolve, 100));

  assert.equal(hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-r"), false);
  assert.equal(hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-r"), false);
});

test("sends idle heartbeats at the interval negotiated by the hub", async (t) => {
  const hub = startHub({ heartbeatIntervalMs: 30 });
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => null,
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  await waitUntil(() => hub.messages.some((m) => m.type === "heartbeat" && m.status === "idle"));
});

test("reports step events with increasing sequence and unique event ids before summary", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: (run) => {
        run.report("step_started", "步骤一", "started", "开始执行");
        run.report("step_completed", "步骤一", "completed", "执行完成");
        return { ok: true };
      },
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({ type: "dispatch", runId: "run-steps", capability: "query_control_platform", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-steps"));

  const events = hub.messages.filter((m) => m.type === "run_event" && m.runId === "run-steps");
  const stepStarted = events.find((m) => m.event === "step_started");
  const stepCompleted = events.find((m) => m.event === "step_completed");
  assert.ok(stepStarted);
  assert.ok(stepCompleted);
  for (let i = 1; i < events.length; i += 1) {
    assert.ok(events[i].seq > events[i - 1].seq);
  }
  assert.equal(new Set(events.map((m) => m.eventId)).size, events.length);

  const summaryIndex = hub.messages.findIndex(
    (m) => m.type === "run_event" && m.event === "run_summary" && m.runId === "run-steps",
  );
  const completeIndex = hub.messages.findIndex((m) => m.type === "run_complete" && m.runId === "run-steps");
  assert.ok(summaryIndex >= 0);
  assert.ok(summaryIndex < completeIndex);
});

test("reconnects and re-registers after the socket closes", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => null,
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  assert.equal(registerMessages(hub).length, 1);

  hub.disconnectClient();
  await waitUntil(() => registerMessages(hub).length >= 2, 5000);
  await waitUntil(() => connection.isRegistered());
  assert.ok(hub.connectionCount >= 2);
});

test("uses per-system token headers when configured, falls back to legacy token", async (t) => {
  const hub = startHub();
  const port = await hub.ready;

  const systemConnection = new HubConnection({
    config: createConfig(port, { systemId: "control-platform", systemToken: "sys-token-1" }),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => null,
      onRecall: () => {},
    },
  });
  t.after(async () => {
    systemConnection.stop();
    await hub.close();
  });

  systemConnection.start();
  await waitUntil(() => systemConnection.isRegistered());
  assert.equal(hub.systemHeaders.length, 1);
  assert.equal(hub.systemHeaders[0].systemId, "control-platform");
  assert.equal(hub.systemHeaders[0].systemToken, "sys-token-1");
  assert.equal(hub.tokens[0], undefined);
  systemConnection.stop();
  await hub.close();
});

test("falls back to legacy execution token headers without system config", async (t) => {
  const hub = startHub();
  const port = await hub.ready;

  const legacyConnection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => null,
      onRecall: () => {},
    },
  });
  t.after(async () => {
    legacyConnection.stop();
    await hub.close();
  });

  legacyConnection.start();
  await waitUntil(() => legacyConnection.isRegistered());
  assert.equal(hub.tokens[0], "test-token");
  assert.equal(hub.systemHeaders[0].systemId, undefined);
  legacyConnection.stop();
  await hub.close();
});

test("carries request_id and target_agent_ref into the run context", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  let dispatchedRun;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "reason_control_platform" }],
      onDispatch: async (run) => {
        dispatchedRun = run;
        return { ok: true };
      },
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({
    type: "dispatch",
    runId: "run-meta",
    capability: "reason_control_platform",
    input: { task_type: "order_delivery_analysis" },
    request_id: "dispatch-req-1",
    target_agent_ref: "spc-agent-order-risk",
    traceId: "trace-meta",
  });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-meta"));

  assert.equal(dispatchedRun.source, "hub");
  assert.equal(dispatchedRun.requestId, "dispatch-req-1");
  assert.equal(dispatchedRun.targetAgentRef, "spc-agent-order-risk");
  const complete = hub.messages.find((m) => m.type === "run_complete" && m.runId === "run-meta");
  assert.deepEqual(complete.result, { ok: true });
});

test("maps RATE_LIMITED to AGENT_BUSY in run_failed", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => {
        const error = new Error("too many");
        error.code = "RATE_LIMITED";
        throw error;
      },
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({ type: "dispatch", runId: "run-rate", capability: "query_control_platform", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-rate"));

  const failed = hub.messages.find((m) => m.type === "run_failed" && m.runId === "run-rate");
  assert.equal(failed.error.code, "AGENT_BUSY");
});

test("rejects unknown capabilities with AGENT_NOT_FOUND", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => ({ ok: true }),
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({ type: "dispatch", runId: "run-unknown", capability: "nope", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-unknown"));

  const failed = hub.messages.find((m) => m.type === "run_failed" && m.runId === "run-unknown");
  assert.equal(failed.error.code, "AGENT_NOT_FOUND");
});

test("rejects non-string target_agent_ref with INVALID_ARGUMENT", async (t) => {
  const hub = startHub();
  const port = await hub.ready;
  const connection = new HubConnection({
    config: createConfig(port),
    log: () => {},
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => ({ ok: true }),
      onRecall: () => {},
    },
  });
  t.after(async () => {
    connection.stop();
    await hub.close();
  });

  connection.start();
  await waitUntil(() => connection.isRegistered());
  hub.send({
    type: "dispatch",
    runId: "run-bad-target",
    capability: "query_control_platform",
    input: {},
    target_agent_ref: 123,
  });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-bad-target"));

  const failed = hub.messages.find((m) => m.type === "run_failed" && m.runId === "run-bad-target");
  assert.equal(failed.error.code, "INVALID_ARGUMENT");
});
