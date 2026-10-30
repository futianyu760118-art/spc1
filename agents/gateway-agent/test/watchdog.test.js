"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { startWatchdog } = require("../src/watchdog");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function baseGateway(overrides = {}) {
  return {
    healthCheckPort: 0,
    watchdogRunMaxMs: 0,
    watchdogSelfPingIntervalMs: 0,
    watchdogSelfPingTimeoutMs: 0,
    watchdogSelfPingMaxFailures: 1,
    watchdogLoopStallMs: 0,
    ...overrides,
  };
}

test("run 超过 watchdogRunMaxMs 触发退出", async () => {
  const exits = [];
  const startedAt = new Date(Date.now() - 60_000);
  const connection = {
    hubRun: { runId: "run-1", capability: "query_control_platform", startedAt },
    localRuns: new Map(),
  };
  const watchdog = startWatchdog({
    log: () => {},
    gateway: baseGateway({ watchdogRunMaxMs: 1000 }),
    connection,
    exit: (code) => exits.push(code),
    runCheckIntervalMs: 20,
  });
  await sleep(120);
  watchdog.stop();
  assert.deepEqual(exits, [1]);
});

test("健康口连续无响应达到 maxFailures 触发退出", async () => {
  const exits = [];
  const watchdog = startWatchdog({
    log: () => {},
    gateway: baseGateway({
      healthCheckPort: 1, // 保留端口，连接必然被拒
      watchdogSelfPingIntervalMs: 20,
      watchdogSelfPingTimeoutMs: 20,
      watchdogSelfPingMaxFailures: 2,
    }),
    connection: { hubRun: null, localRuns: new Map() },
    exit: (code) => exits.push(code),
  });
  await sleep(200);
  watchdog.stop();
  assert.deepEqual(exits, [1]);
});

test("健康口返回任意 HTTP 响应（含 503）不触发退出", async () => {
  const server = http.createServer((req, res) => {
    res.writeHead(503, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "not_registered" }));
  });
  const ready = new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
  const port = await ready;
  const exits = [];
  const watchdog = startWatchdog({
    log: () => {},
    gateway: baseGateway({
      healthCheckPort: port,
      watchdogSelfPingIntervalMs: 20,
      watchdogSelfPingTimeoutMs: 20,
      watchdogSelfPingMaxFailures: 2,
    }),
    connection: { hubRun: null, localRuns: new Map() },
    exit: (code) => exits.push(code),
  });
  await sleep(200);
  watchdog.stop();
  server.close();
  assert.deepEqual(exits, []);
});

test("事件循环停摆标志由主循环 tick 检出并触发退出", async () => {
  const exits = [];
  const watchdog = startWatchdog({
    log: () => {},
    gateway: baseGateway(),
    connection: { hubRun: null, localRuns: new Map() },
    exit: (code) => exits.push(code),
  });
  assert.ok(watchdog.loopFlag, "未启用 stall 检测时应仍创建共享标志");
  watchdog.loopFlag[1] = 1; // 模拟 worker 线程举报主循环停摆
  await sleep(600);
  watchdog.stop();
  assert.deepEqual(exits, [1]);
});

test("stop() 之后不再触发退出", async () => {
  const exits = [];
  const watchdog = startWatchdog({
    log: () => {},
    gateway: baseGateway({
      healthCheckPort: 1,
      watchdogSelfPingIntervalMs: 20,
      watchdogSelfPingTimeoutMs: 20,
      watchdogSelfPingMaxFailures: 2,
    }),
    connection: { hubRun: null, localRuns: new Map() },
    exit: (code) => exits.push(code),
  });
  watchdog.stop();
  await sleep(150);
  assert.deepEqual(exits, []);
});
