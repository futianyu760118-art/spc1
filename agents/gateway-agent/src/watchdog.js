"use strict";

const http = require("node:http");
const { Worker } = require("node:worker_threads");

// 看门狗：网关"WS 在线但派单无响应"（Hub UAT 2026-10-28 问题二）的自愈机制。
// 三层检测，任一触发即 process.exit(1)，由 Docker restart 策略拉起：
//  1. run 卡死占坑：单一 hubRun 被挂起的适配器永久占用 → 后续派单全部 AGENT_BUSY；
//  2. 健康口失联：health server 不再响应自检请求 → 管理面/本地 run 全部不可用；
//  3. 事件循环停摆：主线程被同步阻塞 → 定时器全部停摆；由 worker 线程经共享内存
//     举报，主循环恢复后的首个 tick 触发退出（永久阻塞场景由容器层探活兜底）。

const LOOP_PING_INTERVAL_MS = 500;

const WORKER_SCRIPT = `
"use strict";
const { workerData } = require("node:worker_threads");
const flag = new Int32Array(workerData.sab);
for (;;) {
  const result = Atomics.wait(flag, 0, 1, workerData.stallMs);
  if (result === "timed-out") {
    flag[1] = 1;
    console.error(JSON.stringify({
      level: "error", event: "watchdog_trigger", reason: "event_loop_stalled",
      stallMs: workerData.stallMs,
    }));
    process.exit(1);
  }
}
`;

function activeRuns(connection) {
  const runs = [];
  if (connection.hubRun) runs.push(connection.hubRun);
  for (const run of connection.localRuns.values()) runs.push(run);
  return runs;
}

function startWatchdog({
  log,
  gateway,
  connection,
  exit = (code) => process.exit(code),
  runCheckIntervalMs = 30_000,
}) {
  const stallMs = Number(gateway.watchdogLoopStallMs ?? 0);
  const selfPingIntervalMs = Number(gateway.watchdogSelfPingIntervalMs ?? 0);
  const selfPingTimeoutMs = Number(gateway.watchdogSelfPingTimeoutMs ?? 5000);
  const selfPingMaxFailures = Number(gateway.watchdogSelfPingMaxFailures ?? 3);
  const runMaxMs = Number(gateway.watchdogRunMaxMs ?? 0);

  // 单次触发自锁：exit 之后进程理应终止；注入 exit 的测试环境里防止定时器重复触发
  let triggered = false;
  const trigger = (reason, detail = {}) => {
    if (triggered) return;
    triggered = true;
    log("error", "watchdog_trigger", { reason, ...detail });
    exit(1);
  };

  // ── 1. run 卡死占坑 ──
  let runTimer = null;
  if (runMaxMs > 0) {
    runTimer = setInterval(() => {
      for (const run of activeRuns(connection)) {
        if (!run.startedAt) continue;
        const ageMs = Date.now() - run.startedAt.getTime();
        if (ageMs > runMaxMs) {
          trigger("run_exceeded_max", { runId: run.runId, capability: run.capability, ageMs });
          return;
        }
      }
    }, runCheckIntervalMs);
    runTimer.unref();
  }

  // ── 2. 健康口自检 ──
  let pingTimer = null;
  let pingFailures = 0;
  if (selfPingIntervalMs > 0 && gateway.healthCheckPort > 0) {
    pingTimer = setInterval(() => {
      const req = http.get(
        { host: "127.0.0.1", port: gateway.healthCheckPort, path: "/healthz", timeout: selfPingTimeoutMs },
        (res) => {
          res.resume();
          // 任意 HTTP 响应（含未注册 503）都证明 health server 活着；注册状态由连接层自愈
          pingFailures = 0;
        },
      );
      req.on("timeout", () => {
        req.destroy();
        pingFailures += 1;
        if (pingFailures >= selfPingMaxFailures) {
          trigger("health_self_ping_failed", { failures: pingFailures });
        }
      });
      req.on("error", () => {
        pingFailures += 1;
        if (pingFailures >= selfPingMaxFailures) {
          trigger("health_self_ping_failed", { failures: pingFailures });
        }
      });
    }, selfPingIntervalMs);
    pingTimer.unref();
  }

  // ── 3. 事件循环停摆 ──
  // 标志与主循环 tick 恒在（便于测试与未来复用）；仅 stallMs>0 时启动 worker 线程举报
  let worker = null;
  let loopPingTimer = null;
  const loopFlag = new Int32Array(new SharedArrayBuffer(8));
  loopFlag[0] = 1;
  if (stallMs > 0) {
    worker = new Worker(WORKER_SCRIPT, { eval: true, workerData: { sab: loopFlag.buffer, stallMs } });
    worker.unref();
  }
  loopPingTimer = setInterval(() => {
    if (loopFlag[1] === 1) trigger("event_loop_stalled", { stallMs });
    Atomics.store(loopFlag, 0, 1);
    Atomics.notify(loopFlag, 0);
  }, LOOP_PING_INTERVAL_MS);
  loopPingTimer.unref();

  return {
    loopFlag,
    stop() {
      if (runTimer) clearInterval(runTimer);
      if (pingTimer) clearInterval(pingTimer);
      if (loopPingTimer) clearInterval(loopPingTimer);
      if (worker) void worker.terminate();
    },
  };
}

module.exports = { startWatchdog };
