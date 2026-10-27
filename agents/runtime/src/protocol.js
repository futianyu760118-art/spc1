"use strict";

const WebSocket = require("ws");

/**
 * AEOS Hub 执行面 WS 协议状态机 —— 信封对齐 execution-agent/src/ws-client.js
 * （真实契约联调过的参照实现），字段如有出入以 Hub 契约文档为准、只改本文件。
 *
 * 连接：握手头 x-aeos-execution-token → register {agentId,name,version,sourceSystem?,capabilities}
 * Hub：registered {agentId,heartbeatIntervalMs} → 周期 heartbeat {status,currentRunId?}
 * 派单：dispatch {runId,capability,input} → run_update{running} → run_complete|run_failed
 * 步骤上报：run 期间以 run_event 上报 run_received/step_started/step_completed/error/run_summary，
 *   Hub 回 run_event_ack（仅排查用，不阻塞任务）
 * 召回：recall {runId} → 中止活动 run（含平台侧推理取消），不回报（契约 §5）
 * 断线：杀活动 run（不回报）→ 1/2/5/10/30s 阶梯 + ±20% 抖动重连后重新 register
 * 单活动 run：忙时新 dispatch 回 run_failed(INTERNAL_ERROR 'agent busy')（设计 §3 边界决策）
 */
const RECONNECT_LADDER_MS = [1000, 2000, 5000, 10000, 30000];
const DEFAULT_HEARTBEAT_MS = 5000;
const CALLER_KEYS = ["systemId", "agentId", "userId", "taskId", "traceId"];

function normalizeCaller(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const caller = {};
  for (const key of CALLER_KEYS) {
    const raw = value[key];
    if (raw === undefined || raw === null || String(raw).trim() === "") continue;
    caller[key] = String(raw).trim();
  }
  return Object.keys(caller).length ? caller : null;
}

function traceFields(run) {
  if (!run) return {};
  const fields = {};
  if (run.traceId) fields.traceId = run.traceId;
  if (run.taskId) fields.taskId = run.taskId;
  return fields;
}

class HubConnection {
  constructor({ config, log, handlers }) {
    this.config = config;
    this.log = log;
    this.handlers = handlers;
    this.socket = null;
    this.heartbeatTimer = null;
    this.heartbeatIntervalMs = DEFAULT_HEARTBEAT_MS;
    this.registered = false;
    this.reconnectStep = 0;
    this.reconnectTimer = null;
    this.stopped = false;
    this.hubRun = null;
    this.localRuns = new Map();
    this.runs = new Map();
    this.runSeq = new Map();
  }

  start() {
    this.stopped = false;
    // 本地模式：EXECUTION_WS_URL 为空时不连 Hub，仅保留 /admin/run 本地派单能力
    if (!this.config.wsUrl) {
      this.log("info", "hub_disabled_local_mode", { agentKey: this.config.agentKey });
      return;
    }
    this.connect();
  }

  stop() {
    this.stopped = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.stopHeartbeat();
    this.abortActive("agent shutdown");
    if (this.socket) {
      try {
        this.socket.close(1000, "agent shutdown");
      } catch {
        /* 已关闭 */
      }
    }
  }

  isRegistered() {
    return this.registered;
  }

  connect() {
    if (this.stopped) return;
    // 每系统令牌模式优先（x-aeos-system-id/token，Hub system-token 鉴权）；
    // 未配置时回退 legacy 根令牌（x-aeos-execution-token）
    const headers =
      this.config.systemId && this.config.systemToken
        ? { "x-aeos-system-id": this.config.systemId, "x-aeos-system-token": this.config.systemToken }
        : { "x-aeos-execution-token": this.config.token };
    const socket = new WebSocket(this.config.wsUrl, { headers });
    this.socket = socket;

    socket.on("open", () => {
      this.log("info", "hub_connected", { wsUrl: this.config.wsUrl });
      this.send({
        type: "register",
        agentId: this.config.agentId,
        name: this.config.agentName,
        version: this.config.agentVersion,
        ...(this.config.sourceSystem ? { sourceSystem: this.config.sourceSystem } : {}),
        capabilities: this.handlers.capabilities.map((c) => ({ ...c, version: this.config.agentVersion })),
      });
    });

    socket.on("message", (raw) => {
      let message;
      try {
        message = JSON.parse(raw.toString());
      } catch {
        this.log("warn", "hub_bad_message", { raw: String(raw).slice(0, 200) });
        return;
      }
      if (message && typeof message === "object") this.handleMessage(message);
    });

    socket.on("error", (e) => this.log("warn", "hub_socket_error", { message: e.message }));

    socket.on("close", () => {
      const wasRegistered = this.registered;
      this.registered = false;
      this.stopHeartbeat();
      this.abortActive("disconnected");
      if (this.stopped) return;
      this.log("warn", "hub_disconnected", { wasRegistered });
      this.scheduleReconnect();
    });
  }

  handleMessage(message) {
    if (message && typeof message === "object" && message.type !== "heartbeat") {
      this.log("info", "hub_message_received", {
        type: message.type,
        runId: message.runId ?? null,
        capability: message.capability ?? null,
      });
    }
    switch (message.type) {
      case "registered": {
        const interval = Number(message.heartbeatIntervalMs);
        this.heartbeatIntervalMs = Number.isFinite(interval) && interval > 0 ? interval : DEFAULT_HEARTBEAT_MS;
        this.registered = true;
        this.reconnectStep = 0;
        this.startHeartbeat();
        this.log("info", "hub_registered", { agentId: message.agentId, heartbeatIntervalMs: this.heartbeatIntervalMs });
        break;
      }
      case "dispatch":
        this.onDispatch(message);
        break;
      case "recall":
        this.onRecall(message.runId);
        break;
      case "error":
        this.log("warn", "hub_protocol_error", { message: message.message });
        break;
      case "run_event_ack":
        if (message.accepted !== true) {
          this.log("warn", "run_event_rejected", { runId: message.runId, eventId: message.eventId, reason: message.reason });
        }
        break;
      default:
        this.log("warn", "hub_unknown_message_type", { type: message.type });
    }
  }

  onDispatch(dispatch) {
    const { runId, capability } = dispatch ?? {};
    if (!runId) return;
    this.log("info", "dispatch_received", {
      runId,
      capability,
      traceId: dispatch.traceId ?? null,
      caller: normalizeCaller(dispatch.caller),
    });
    if (this.hubRun) {
      this.log("warn", "dispatch_rejected", { runId, reason: "busy", currentRunId: this.hubRun.runId });
      this.send({ type: "run_failed", runId, error: { code: "INTERNAL_ERROR", message: "agent busy" } });
      return;
    }
    if (!this.handlers.capabilities.some((c) => c.name === capability)) {
      this.log("warn", "dispatch_rejected", { runId, reason: "unknown_capability", capability });
      this.send({ type: "run_failed", runId, error: { code: "INVALID_ARGUMENT", message: `未知 capability: ${capability}` } });
      return;
    }

    const caller = normalizeCaller(dispatch.caller);
    const traceId = dispatch.traceId || (caller && caller.traceId) || runId;
    const taskId = caller && caller.taskId ? caller.taskId : null;
    const run = {
      runId,
      capability,
      caller,
      traceId,
      taskId,
      recalled: false,
      controller: new AbortController(),
      report: (event, name, status, summary, detail, timings) =>
        this.reportRunEvent(runId, event, name, status, summary, detail, timings),
    };
    this.hubRun = run;
    this.runs.set(runId, run);
    this.reportRunEvent(runId, "run_received", "收到任务", "info", `capability=${capability}`, {
      capability,
      path: dispatch.input?.path,
    });
    this.send({ type: "run_update", runId, ...traceFields(run), state: "running" });
    this.log("info", "run_started", { runId, capability });

    Promise.resolve()
      .then(() => this.handlers.onDispatch(run, dispatch.input))
      .then((outcome) => {
        // null = 推理任务被召回/取消（契约 §5：召回不回报）；recalled 同样跳过
        if (run.recalled || outcome === null || outcome === undefined) return;
        // 适配器可返回 { result, usage }（推理用量记 Hub 台账）；其余直接当 result
        const withUsage =
          outcome && typeof outcome === "object" && "usage" in outcome && outcome.usage != null;
        const result = withUsage ? outcome.result : outcome;
        const usage = withUsage ? outcome.usage : undefined;
        const summary = `任务完成：${capability}`;
        this.reportRunEvent(runId, "run_summary", "任务完成", "completed", summary);
        this.send({ type: "run_complete", runId, ...traceFields(run), result, ...(usage ? { usage } : {}) });
        this.log("info", "run_complete", { runId });
      })
      .catch((e) => {
        if (run.recalled) return;
        this.reportRunEvent(runId, "run_summary", "任务失败", "failed", e.message);
        this.send({ type: "run_failed", runId, error: { code: e.code || "INTERNAL_ERROR", message: e.message } });
        this.log("info", "run_failed", { runId, code: e.code || "INTERNAL_ERROR" });
      })
      .finally(() => {
        if (this.hubRun === run) this.hubRun = null;
        this.runs.delete(run.runId);
        this.runSeq.delete(run.runId);
      });
  }

  onRecall(runId) {
    const run = this.hubRun;
    if (!run) {
      this.log("warn", "recall_ignored_no_active_run", { runId: runId ?? null });
      return;
    }
    if (runId && run.runId !== runId) {
      this.log("warn", "recall_ignored_run_mismatch", { runId, currentRunId: run.runId });
      return;
    }
    run.recalled = true;
    this.log("info", "run_recalled", { runId: run.runId });
    run.controller.abort();
    this.handlers.onRecall(run.runId);
  }

  abortActive(reason) {
    const runs = [];
    if (this.hubRun) runs.push(this.hubRun);
    for (const run of this.localRuns.values()) runs.push(run);
    for (const run of runs) {
      run.recalled = true;
      this.log("info", "run_aborted", { runId: run.runId, reason });
      run.controller.abort();
      this.handlers.onRecall(run.runId);
    }
  }

  send(payload) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(payload));
    else this.log("warn", "send_skipped_not_open", { type: payload.type });
  }

  /** 执行步骤上报：事件按 runId 内 seq 递增、eventId 唯一（Hub 端去重）；
   *  timings 只给 startedAt 即自动推导 endedAt/durationMs，status=started 的事件恒不补 endedAt。 */
  reportRunEvent(runId, event, name, status, summary, detail = null, timings = {}) {
    const startedAt = timings.startedAt ?? null;
    const endedAt = timings.endedAt ?? (startedAt && status !== "started" ? new Date().toISOString() : null);
    const durationMs =
      timings.durationMs ??
      (startedAt && endedAt ? new Date(endedAt).getTime() - new Date(startedAt).getTime() : null);
    const seq = (this.runSeq.get(runId) ?? 0) + 1;
    this.runSeq.set(runId, seq);
    this.send({
      type: "run_event",
      runId,
      ...traceFields(this.runs.get(runId)),
      eventId: `evt-${runId}-${seq}`,
      seq,
      event,
      name,
      status,
      summary,
      detail,
      startedAt,
      endedAt,
      durationMs,
    });
  }

  startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      const message = {
        type: "heartbeat",
        status: this.hubRun ? "working" : "idle",
      };
      if (this.hubRun) message.currentRunId = this.hubRun.runId;
      this.send(message);
    }, this.heartbeatIntervalMs);
  }

  stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  scheduleReconnect() {
    const base = RECONNECT_LADDER_MS[Math.min(this.reconnectStep, RECONNECT_LADDER_MS.length - 1)];
    this.reconnectStep = Math.min(this.reconnectStep + 1, RECONNECT_LADDER_MS.length - 1);
    const delay = Math.round(base * (0.8 + Math.random() * 0.4));
    this.log("info", "hub_reconnect_scheduled", { attempt: this.reconnectStep + 1, delayMs: delay });
    this.reconnectTimer = setTimeout(() => {
      if (!this.stopped) this.connect();
    }, delay);
  }
}

module.exports = { HubConnection, normalizeCaller };
