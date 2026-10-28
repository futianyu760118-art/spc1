"use strict";

const { UpstreamError, mapCode } = require("@spc/execution-agent-runtime");

const OPERATIONS = Object.freeze([
  "order.update_note",
  "order.update_status",
  "order.update_delivery_date",
]);
const STATUS_VALUES = Object.freeze(["open", "closed"]);
const REMARK_MAX_LENGTH = 2000;
const IDEMPOTENCY_KEY_MAX_LENGTH = 128;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const OPERATIONS_METADATA = Object.freeze([
  {
    name: "order.update_note",
    title: "修改订单备注",
    keywords: ["备注", "说明"],
    changesField: "changes",
    fields: [{ name: "remark", label: "备注", type: "string", required: true }],
  },
  {
    name: "order.update_status",
    title: "修改订单状态",
    keywords: ["状态"],
    changesField: "changes",
    fields: [{ name: "status", label: "状态", type: "string", required: true }],
  },
  {
    name: "order.update_delivery_date",
    title: "修改交付日期",
    keywords: ["交付日期", "交期"],
    changesField: "changes",
    fields: [{ name: "deliveryDate", label: "交付日期", type: "date", required: true }],
  },
]);

const inputSchema = Object.freeze({
  type: "object",
  properties: {
    operation: { type: "string", enum: [...OPERATIONS] },
    orderNo: { type: "string", minLength: 1, maxLength: 64 },
    changes: {
      type: "object",
      properties: {
        remark: { type: ["string", "null"], maxLength: REMARK_MAX_LENGTH },
        status: { type: "string", enum: [...STATUS_VALUES] },
        deliveryDate: { type: "string", format: "date", pattern: "^\\d{4}-\\d{2}-\\d{2}$" },
      },
      additionalProperties: false,
    },
    idempotencyKey: { type: "string", maxLength: IDEMPOTENCY_KEY_MAX_LENGTH },
  },
  required: ["operation", "orderNo", "changes"],
});

const outputSchema = Object.freeze({
  type: "object",
  properties: {
    ok: { type: "boolean" },
    operation: { type: "string" },
    target: { type: "object" },
    before: { type: "object" },
    after: { type: "object" },
    appliedAt: { type: "string" },
    idempotent_replay: { type: "boolean" },
    request_id: { type: "string" },
    handled_by: { type: "object" },
  },
  required: ["ok", "operation", "target", "before", "after", "appliedAt", "idempotent_replay"],
});

function isValidIsoDate(value) {
  if (typeof value !== "string" || !DATE_RE.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

function validateInput(input, run) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new UpstreamError("INVALID_ARGUMENT", "input 必须是对象");
  }
  const operation = input.operation;
  if (!OPERATIONS.includes(operation)) {
    throw new UpstreamError("CAPABILITY_UNSUPPORTED", `不支持的操作：${operation}`);
  }
  if (typeof input.orderNo !== "string" || !input.orderNo.trim()) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.orderNo 不能为空");
  }
  const orderNo = input.orderNo.trim();
  if (orderNo.length > 64) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.orderNo 不能超过 64 字符");
  }
  const changes = input.changes;
  if (!changes || typeof changes !== "object" || Array.isArray(changes)) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.changes 必须是对象");
  }
  if (operation === "order.update_note") {
    const keys = Object.keys(changes);
    if (keys.length !== 1 || keys[0] !== "remark") {
      throw new UpstreamError("INVALID_ARGUMENT", "order.update_note 只允许 changes.remark");
    }
    const remark = changes.remark;
    if (remark !== null && typeof remark !== "string") {
      throw new UpstreamError("INVALID_ARGUMENT", "changes.remark 必须是字符串或 null");
    }
    if (typeof remark === "string" && remark.length > REMARK_MAX_LENGTH) {
      throw new UpstreamError("INVALID_ARGUMENT", `changes.remark 不能超过 ${REMARK_MAX_LENGTH} 字符`);
    }
  } else if (operation === "order.update_status") {
    const keys = Object.keys(changes);
    if (keys.length !== 1 || keys[0] !== "status") {
      throw new UpstreamError("INVALID_ARGUMENT", "order.update_status 只允许 changes.status");
    }
    if (!STATUS_VALUES.includes(changes.status)) {
      throw new UpstreamError("INVALID_ARGUMENT", "changes.status 必须是 open 或 closed");
    }
  } else {
    const keys = Object.keys(changes);
    if (keys.length !== 1 || keys[0] !== "deliveryDate") {
      throw new UpstreamError(
        "INVALID_ARGUMENT",
        "order.update_delivery_date 只允许 changes.deliveryDate",
      );
    }
    if (!isValidIsoDate(changes.deliveryDate)) {
      throw new UpstreamError("INVALID_ARGUMENT", "changes.deliveryDate 必须是 YYYY-MM-DD");
    }
  }
  const idempotencyKey = input.idempotencyKey || run.requestId;
  if (typeof idempotencyKey !== "string" || !idempotencyKey.trim()) {
    throw new UpstreamError("INVALID_ARGUMENT", "缺少 idempotencyKey（或 request_id）");
  }
  if (idempotencyKey.trim().length > IDEMPOTENCY_KEY_MAX_LENGTH) {
    throw new UpstreamError("INVALID_ARGUMENT", `idempotencyKey 不能超过 ${IDEMPOTENCY_KEY_MAX_LENGTH} 字符`);
  }
  return {
    operation,
    orderNo,
    changes,
    idempotencyKey: idempotencyKey.trim(),
  };
}

function mapWriteError(code, message) {
  if (typeof message === "string") {
    if (message.startsWith("IDEMPOTENCY_CONFLICT")) return "IDEMPOTENCY_CONFLICT";
    if (message.startsWith("AGENT_BUSY")) return "AGENT_BUSY";
    if (message.startsWith("CAPABILITY_UNSUPPORTED")) return "CAPABILITY_UNSUPPORTED";
  }
  const mapped = mapCode(code);
  if (mapped === "NOT_FOUND") return "TARGET_NOT_FOUND";
  return mapped;
}

function createAdapter({ config, http, log }) {
  const capability = {
    name: "write_control_platform",
    description: "中台受控写操作（订单备注/状态/交付日期），仅接受 Hub 审批后的派单",
    readOnly: false,
    constraints: {
      readOnly: false,
      approvalRequired: true,
      riskLevel: "low",
      idempotent: true,
      dryRun: false,
    },
    inputSchema,
    outputSchema,
    operations: OPERATIONS_METADATA,
  };

  async function invoke(run, input) {
    const parsed = validateInput(input, run);
    const path = `/external/orders/${encodeURIComponent(parsed.orderNo)}/write`;
    const body = {
      operation: parsed.operation,
      changes: parsed.changes,
      idempotencyKey: parsed.idempotencyKey,
    };
    if (run.requestId) body.request_id = run.requestId;
    else if (input.request_id !== undefined) body.request_id = input.request_id;

    const report = run.report;
    const startedAt = new Date().toISOString();
    report(
      "step_started",
      "受控写操作",
      "started",
      `${parsed.operation} ${parsed.orderNo}`,
      { operation: parsed.operation, orderNo: parsed.orderNo },
      { startedAt },
    );
    log("info", "order_write_started", {
      operation: parsed.operation,
      orderNo: parsed.orderNo,
      idempotencyKey: parsed.idempotencyKey,
    });

    const headers = { "X-Agent-Run-Id": run.runId };
    if (run.actorToken) headers["X-Actor-Token"] = run.actorToken;
    const operatorUserId = run.operator && run.operator.user_id;
    if (operatorUserId) headers["X-Operator-User-Id"] = String(operatorUserId);
    const hubCallerUserId = run.caller && run.caller.userId;
    if (hubCallerUserId) headers["X-Hub-Caller-User-Id"] = hubCallerUserId;

    let envelope;
    try {
      envelope = await http.signedSendEnvelope("PUT", path, "orders.write", body, {
        signal: run.controller.signal,
        timeoutMs: config.writeTimeoutMs,
        headers,
      });
    } catch (e) {
      if (e.code === "ABORTED") return null;
      report(
        "error",
        "受控写操作",
        "failed",
        e.message,
        { operation: parsed.operation, orderNo: parsed.orderNo, code: e.code },
        { startedAt },
      );
      throw e;
    }
    if (envelope.code === 0) {
      report(
        "step_completed",
        "受控写操作",
        "completed",
        `${parsed.operation} ${parsed.orderNo} 已完成`,
        { operation: parsed.operation, orderNo: parsed.orderNo },
        { startedAt },
      );
      log("info", "order_write_ok", {
        operation: parsed.operation,
        orderNo: parsed.orderNo,
      });
      return envelope.data ?? {};
    }
    const message = envelope.message || `中台返回 code=${envelope.code}`;
    const code = mapWriteError(envelope.code, message);
    report(
      "error",
      "受控写操作",
      "failed",
      message,
      { operation: parsed.operation, orderNo: parsed.orderNo, code },
      { startedAt },
    );
    throw new UpstreamError(code, message);
  }

  return { capability, invoke };
}

module.exports = {
  createAdapter,
  OPERATIONS,
  OPERATIONS_METADATA,
  STATUS_VALUES,
  inputSchema,
  outputSchema,
  mapWriteError,
};
