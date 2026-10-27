"use strict";

const { UpstreamError, mapCode } = require("@spc/execution-agent-runtime");

const ALLOWED_FIELDS = Object.freeze([
  "shipping_plan",
  "delivery_completed_date",
  "customer_inspection_date",
  "planned_start_date",
]);

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const inputSchema = Object.freeze({
  type: "object",
  properties: {
    order_no: { type: "string", minLength: 1, description: "销售订单号（精确匹配，取最新一条）" },
    fields: {
      type: "object",
      description: "可写字段白名单；值为 YYYY-MM-DD 或 null（清空）；至少一个键",
      properties: {
        shipping_plan: { type: ["string", "null"], description: "出货计划" },
        delivery_completed_date: { type: ["string", "null"], description: "发货完成时间" },
        customer_inspection_date: { type: ["string", "null"], description: "客户验货时间" },
        planned_start_date: { type: ["string", "null"], description: "上线时间" },
      },
      additionalProperties: false,
      minProperties: 1,
    },
    request_id: { type: "string", maxLength: 128 },
  },
  required: ["order_no", "fields"],
});

const outputSchema = Object.freeze({
  type: "object",
  properties: {
    order_no: { type: "string" },
    fields: { type: "object", description: "四字段更新后快照" },
    updated_at: { type: "string" },
  },
  required: ["order_no"],
});

function validateInput(input) {
  if (!input || typeof input !== "object") {
    throw new UpstreamError("INVALID_ARGUMENT", "input 必须是对象");
  }
  if (typeof input.order_no !== "string" || !input.order_no.trim()) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.order_no 不能为空");
  }
  const fields = input.fields;
  if (!fields || typeof fields !== "object" || Array.isArray(fields)) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.fields 必须是对象");
  }
  const keys = Object.keys(fields);
  if (keys.length === 0) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.fields 至少一个字段");
  }
  for (const key of keys) {
    if (!ALLOWED_FIELDS.includes(key)) {
      throw new UpstreamError("INVALID_ARGUMENT", `字段不在白名单：${key}`);
    }
    const value = fields[key];
    if (value !== null && (typeof value !== "string" || !DATE_RE.test(value))) {
      throw new UpstreamError("INVALID_ARGUMENT", `字段 ${key} 必须是 YYYY-MM-DD 或 null`);
    }
  }
}

function createAdapter({ config, http, log }) {
  const capability = {
    name: "update_control_platform_order",
    description: "更新订单出货计划/发货完成/客户验货/上线时间（写能力，字段白名单）",
    readOnly: false,
    constraints: { readOnly: false, allowedFields: [...ALLOWED_FIELDS] },
    inputSchema,
    outputSchema,
  };

  async function invoke(run, input) {
    validateInput(input);
    const orderNo = input.order_no.trim();
    const path = `/external/orders/${encodeURIComponent(orderNo)}/schedule`;
    const body = { fields: input.fields };
    if (input.request_id !== undefined) body.request_id = input.request_id;
    const report = run.report;
    const startedAt = new Date().toISOString();
    report("step_started", "写入订单字段", "started", `order_no=${orderNo}`, { orderNo }, { startedAt });
    log("info", "order_write_started", { orderNo });
    const headers = { "X-Agent-Run-Id": run.runId };
    if (run.actorToken) headers["X-Actor-Token"] = run.actorToken;
    const operatorUserId = run.operator && run.operator.user_id;
    if (operatorUserId) headers["X-Operator-User-Id"] = String(operatorUserId);
    let envelope;
    try {
      envelope = await http.signedSendEnvelope("PUT", path, "orders.schedule.update", body, {
        signal: run.controller.signal,
        timeoutMs: config.writeTimeoutMs,
        headers,
      });
    } catch (e) {
      report("error", "写入订单字段", "failed", e.message, { orderNo, code: e.code }, { startedAt });
      throw e;
    }
    if (envelope.code === 0) {
      report("step_completed", "写入订单字段", "completed", `订单 ${orderNo} 已更新`, { orderNo }, { startedAt });
      log("info", "order_write_ok", { orderNo });
      return envelope.data ?? {};
    }
    const code = mapCode(envelope.code);
    const message = envelope.message || `中台返回 code=${envelope.code}`;
    report("error", "写入订单字段", "failed", message, { orderNo, code }, { startedAt });
    throw new UpstreamError(code, message);
  }

  return { capability, invoke };
}

module.exports = { createAdapter, ALLOWED_FIELDS, inputSchema, outputSchema };
