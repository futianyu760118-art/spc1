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

async function invoke(runId, input, signal) {
  if (!input || typeof input.prompt !== "string" || !input.prompt.trim()) {
    throw new UpstreamError("INVALID_ARGUMENT", "input.prompt 不能为空");
  }
  const body = {
    prompt: input.prompt,
    task_type: input.task_type,
    context: input.context,
    constraints: Object.assign({ read_only: true, require_evidence: true }, input.constraints),
    task_id: runId,
    request_id: input.request_id,
  };
  let envelope;
  try {
    envelope = await signedPostEnvelope(ANALYZE_PATH, "reasoning.analyze", body, { signal });
  } catch (e) {
    if (e.code === "ABORTED") return null;
    throw e;
  }
  if (envelope.code === 0) {
    log("info", "reasoning_ok", { runId, task_type: body.task_type });
    return envelope.data;
  }
  if (envelope.code === 490) return null;
  throw new UpstreamError(
    mapCode(envelope.code),
    envelope.message || `中台推理失败 code=${envelope.code}`,
  );
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

module.exports = { invoke, cancel };
