"use strict";

const { UpstreamError, mapCode } = require("./http-client");
const REGISTRY = require("../../shared/order-write-operations.json");

const OPERATIONS_BY_NAME = new Map(REGISTRY.operations.map((op) => [op.name, op]));
const OPERATIONS = Object.freeze(REGISTRY.operations.map((op) => op.name));
const HUB_OPERATIONS = Object.freeze(
  OPERATIONS.filter((name) => OPERATIONS_BY_NAME.get(name).audiences.includes("hub")),
);
const IDEMPOTENCY_KEY_MAX_LENGTH = 128;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const OPERATIONS_METADATA = Object.freeze(
  REGISTRY.operations
    .filter((op) => op.audiences.includes("hub"))
    .map((op) => ({
      name: op.name,
      title: op.title,
      keywords: op.keywords,
      changesField: "changes",
      fields: op.hubFields,
    })),
);

const inputSchema = Object.freeze({
  type: "object",
  properties: {
    operation: { type: "string", enum: [...HUB_OPERATIONS] },
    orderNo: { type: "string", minLength: 1, maxLength: 64 },
    changes: {
      type: "object",
      properties: Object.fromEntries(
        REGISTRY.operations
          .filter((op) => op.audiences.includes("hub"))
          .map((op) => [op.changesKey, schemaProperty(op.value)]),
      ),
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

function schemaProperty(value) {
  if (value.type === "string_or_null") {
    return { type: ["string", "null"], maxLength: value.maxLength };
  }
  if (value.type === "enum") {
    return { type: "string", enum: value.values };
  }
  if (value.type === "date_map") {
    return { type: "object", additionalProperties: { type: ["string", "null"] } };
  }
  return { type: "string", format: "date", pattern: "^\\d{4}-\\d{2}-\\d{2}$" };
}

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

function validateScalarValue(kind, key, value, spec) {
  if (kind === "string_or_null") {
    if (value !== null && typeof value !== "string") {
      throw new UpstreamError("INVALID_ARGUMENT", `changes.${key} 必须是字符串或 null`);
    }
    if (typeof value === "string" && value.length > spec.maxLength) {
      throw new UpstreamError("INVALID_ARGUMENT", `changes.${key} 不能超过 ${spec.maxLength} 字符`);
    }
    return;
  }
  if (kind === "enum") {
    if (!spec.values.includes(value)) {
      throw new UpstreamError(
        "INVALID_ARGUMENT",
        `changes.${key} 必须是 ${spec.values.join(" 或 ")}`,
      );
    }
    return;
  }
  if (!isValidIsoDate(value)) {
    throw new UpstreamError("INVALID_ARGUMENT", `changes.${key} 必须是 YYYY-MM-DD`);
  }
}

function validateInput(input, run) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new UpstreamError("INVALID_ARGUMENT", "input 必须是对象");
  }
  const operation = input.operation;
  const op = OPERATIONS_BY_NAME.get(operation);
  if (!op) {
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
  const keys = Object.keys(changes);
  const key = op.changesKey;
  if (keys.length !== 1 || keys[0] !== key) {
    throw new UpstreamError("INVALID_ARGUMENT", `${operation} 只允许 changes.${key}`);
  }
  const kind = op.value.type;
  if (kind === "date_map") {
    const fields = changes[key];
    if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
      throw new UpstreamError("INVALID_ARGUMENT", `changes.${key} 必须是对象`);
    }
    const allowed = new Set(op.fields.map((field) => field.wire));
    const fieldKeys = Object.keys(fields);
    if (fieldKeys.length === 0) {
      throw new UpstreamError("INVALID_ARGUMENT", `changes.${key} 至少一个字段`);
    }
    for (const fieldKey of fieldKeys) {
      if (!allowed.has(fieldKey)) {
        throw new UpstreamError("INVALID_ARGUMENT", `字段不在白名单：${fieldKey}`);
      }
      const value = fields[fieldKey];
      if (value !== null && !isValidIsoDate(value)) {
        throw new UpstreamError("INVALID_ARGUMENT", `字段 ${fieldKey} 必须是 YYYY-MM-DD 或 null`);
      }
    }
  } else {
    validateScalarValue(kind, key, changes[key], op.value);
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
    name: REGISTRY.capability,
    description: REGISTRY.capabilityDescription,
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
  REGISTRY,
  HUB_OPERATIONS,
  OPERATIONS,
  OPERATIONS_METADATA,
  inputSchema,
  outputSchema,
  mapWriteError,
};
