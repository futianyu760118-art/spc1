"use strict";

function roundDurationMs(value) {
  return typeof value === "number" && Number.isFinite(value) ? Math.round(value) : value;
}

function normalizeResult(result) {
  if (!result || typeof result !== "object" || Array.isArray(result)) return result;
  if (typeof result.duration_ms !== "number" || !Number.isFinite(result.duration_ms)) return result;
  return { ...result, duration_ms: Math.round(result.duration_ms) };
}

function splitOutcome(outcome) {
  const withUsage =
    outcome &&
    typeof outcome === "object" &&
    !Array.isArray(outcome) &&
    "usage" in outcome &&
    outcome.usage != null;
  return {
    result: withUsage ? outcome.result : outcome,
    usage: withUsage ? outcome.usage : undefined,
  };
}

module.exports = { roundDurationMs, normalizeResult, splitOutcome };
