"use strict";

const { log, UpstreamError, mapCode, signedPostEnvelope } = require("../lib/http-client");

/**
 * 推理适配器（reason_control_platform）—— 真实调用实现。
 *
 * 契约：docs/aeos-reasoning-api-contract.md。映射：
 *   dispatch {runId, input} → POST /external/reasoning/analyze（task_id = runId）；
 *   成功信封 data → run_complete.result；490 取消 / 本地中止 → 返回 null（召回不回报，契约 §5）；
 *   其余信封码 → 契约 §12 错误码（400→INVALID_ARGUMENT / 404→NOT_FOUND /
 *   429→RATE_LIMITED / 503→UPSTREAM_UNAVAILABLE / 504→UPSTREAM_TIMEOUT / 其它→INTERNAL_ERROR）。
 * 召回联动：协议层已中止本地 HTTP，本适配器再 POST reasoning.cancel 让中台同步中断（终态 cancelled）。
 */
const ANALYZE_PATH = "/external/reasoning/analyze";
const TASKS_PATH = "/external/reasoning/tasks";

/** 能力自描述（管理面 127b013 起 register 必带）：结构对齐契约 §3.1 / §3.2。 */
const inputSchema = Object.freeze({
  type: "object",
  properties: {
    prompt: { type: "string", maxLength: 2000, description: "分析问题（必填非空）" },
    task_type: {
      type: "string",
      enum: ["order_delivery_analysis", "material_kitting_analysis", "quality_analysis", "production_analysis"],
    },
    context: {
      type: "object",
      properties: { businessObjectRef: { type: "string", description: "业务锚点 business://<order|product|batch>/<键>" } },
      required: ["businessObjectRef"],
    },
    constraints: {
      type: "object",
      properties: { read_only: { type: "boolean" }, require_evidence: { type: "boolean" } },
      description: "read_only 必须为 true（缺省视为 true）",
    },
    request_id: { type: "string", maxLength: 128 },
  },
  required: ["prompt", "task_type", "context"],
});

const outputSchema = Object.freeze({
  type: "object",
  properties: {
    task_id: { type: "string" },
    task_type: { type: "string" },
    status: { type: "string" },
    summary: { type: "string" },
    conclusions: {
      type: "array",
      items: {
        type: "object",
        properties: {
          matter: { type: "string" },
          evidence_refs: { type: "array", items: { type: "string" } },
          risk: { type: "string" },
          recommendation: { type: "string" },
          confidence: { type: "string" },
        },
      },
    },
    dropped_conclusions: { type: "integer" },
    evidence_refs: { type: "array", items: { type: "string" } },
    data_as_of: { type: "string" },
    data_confidence: { type: "string" },
    stale: { type: "boolean" },
    warnings: { type: "array", items: { type: "string" } },
    duration_ms: { type: "integer" },
    request_id: { type: "string" },
  },
  required: ["task_id", "task_type", "status", "summary"],
});

async function invoke(run, input) {
  if (!input || typeof input.prompt !== "string" || !input.prompt.trim()) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.prompt 不能为空");
  }
  const runId = run.runId;
  const taskType = input.task_type ?? "";
  const body = {
    prompt: input.prompt,
    task_type: input.task_type,
    context: input.context,
    constraints: Object.assign({ read_only: true, require_evidence: true }, input.constraints),
    task_id: runId,
    request_id: input.request_id,
  };
  const report = run.report;
  const startedAt = new Date().toISOString();
  report("step_started", "中台推理分析", "started", `task_type=${taskType}`, { task_type: taskType }, { startedAt });
  let envelope;
  try {
    envelope = await signedPostEnvelope(ANALYZE_PATH, "reasoning.analyze", body, { signal: run.controller.signal });
  } catch (e) {
    if (e.code === "ABORTED") return null;
    report("error", "中台推理分析", "failed", e.message, { task_type: taskType, code: e.code }, { startedAt });
    throw e;
  }
  if (envelope.code === 0) {
    report(
      "step_completed",
      "中台推理分析",
      "completed",
      `结论 ${envelope.data?.conclusions?.length ?? 0} 条`,
      { task_type: taskType, status: envelope.data?.status },
      { startedAt },
    );
    log("info", "reasoning_ok", { runId, task_type: body.task_type });
    // usage 提升为 run_complete 顶层字段（Hub 用量台账），不进 result
    const data = envelope.data ?? {};
    const usage = data && typeof data === "object" && data.usage ? data.usage : undefined;
    const result = { ...data };
    delete result.usage;
    return usage ? { result, usage } : result;
  }
  if (envelope.code === 490) return null;
  const code = mapCode(envelope.code);
  const message = envelope.message || `中台推理失败 code=${envelope.code}`;
  report("error", "中台推理分析", "failed", message, { task_type: taskType, code }, { startedAt });
  throw new UpstreamError(code, message);
}

async function cancel(runId) {
  try {
    await signedPostEnvelope(`${TASKS_PATH}/${encodeURIComponent(runId)}/cancel`, "reasoning.cancel", {});
    log("info", "reasoning_cancel_sent", { runId });
  } catch (e) {
    if (e.code === "ABORTED") return;
    log("warn", "reasoning_cancel_failed", { runId, code: e.code, message: e.message });
  }
}

module.exports = { invoke, cancel, inputSchema, outputSchema };
