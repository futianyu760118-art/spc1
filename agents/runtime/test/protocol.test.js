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
  const gate = new Promise((resolve) => { release = resolve; });
  const connection = new HubConnection({
    config: createConfig(port),
    log: (level, event) => logs.push({ level, event }),
    handlers: {
      capabilities: [{ name: "query_control_platform" }],
      onDispatch: async () => {
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
  await waitUntil(() => connection.isRegistered());

  hub.send({ type: "dispatch", runId: "run-1", capability: "query_control_platform", input: { path: "/external/orders/list" } });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_update" && m.runId === "run-1"));

  hub.send({ type: "dispatch", runId: "run-2", capability: "query_control_platform", input: {} });
  await waitUntil(() => hub.messages.some((m) => m.type === "run_failed" && m.runId === "run-2"));

  release();
  await waitUntil(() => hub.messages.some((m) => m.type === "run_complete" && m.runId === "run-1"));
  const complete = hub.messages.find((m) => m.type === "run_complete" && m.runId === "run-1");
  assert.deepEqual(complete.result, { items: [1] });
  assert.equal(logs.some((l) => l.event === "run_started"), true);
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
  await waitUntil(() => connection.activeRun);
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
