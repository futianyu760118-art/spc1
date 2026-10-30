"use strict";

const { ERROR_CODES } = require("./error-codes");

const CALLER_KEYS = Object.freeze(["systemId", "agentId", "userId", "taskId", "traceId"]);

function normalizeText(value) {
  if (value === undefined || value === null) return null;
  const text = String(value).trim();
  return text || null;
}

function normalizeCaller(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const caller = {};
  for (const key of CALLER_KEYS) {
    const text = normalizeText(value[key]);
    if (text) caller[key] = text;
  }
  return Object.keys(caller).length ? caller : null;
}

function normalizeRequestId(source) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return null;
  const input =
    source.input && typeof source.input === "object" && !Array.isArray(source.input)
      ? source.input
      : null;
  return (
    normalizeText(source.request_id) ??
    normalizeText(source.requestId) ??
    (input ? normalizeText(input.request_id) : null) ??
    (input ? normalizeText(input.requestId) : null)
  );
}

function normalizeTargetAgentRef(source) {
  if (!source || typeof source !== "object" || Array.isArray(source)) return null;
  const raw = source.target_agent_ref ?? source.targetAgentRef;
  if (raw === undefined || raw === null) return null;
  if (typeof raw !== "string") {
    const error = new Error("target_agent_ref 必须是字符串");
    error.code = ERROR_CODES.INVALID_ARGUMENT;
    throw error;
  }
  return normalizeText(raw);
}

function buildRunContext({
  source,
  runId,
  capability,
  input,
  requestId = null,
  traceId = null,
  caller = null,
  targetAgentRef = null,
  operator = null,
  actorToken = null,
  report = null,
}) {
  const normalizedCaller = normalizeCaller(caller);
  return {
    source,
    runId,
    capability,
    input,
    startedAt: new Date(),
    requestId: normalizeText(requestId),
    traceId: normalizeText(traceId),
    taskId: normalizedCaller && normalizedCaller.taskId ? normalizedCaller.taskId : null,
    caller: normalizedCaller,
    targetAgentRef: normalizeText(targetAgentRef),
    operator: operator || null,
    actorToken: actorToken || null,
    recalled: false,
    controller: new AbortController(),
    report: typeof report === "function" ? report : () => {},
  };
}

module.exports = {
  CALLER_KEYS,
  normalizeText,
  normalizeCaller,
  normalizeRequestId,
  normalizeTargetAgentRef,
  buildRunContext,
};
