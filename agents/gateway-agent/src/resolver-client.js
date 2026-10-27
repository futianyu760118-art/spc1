"use strict";

const { UpstreamError } = require("@spc/execution-agent-runtime");

function createResolverClient({ config, log }) {
  async function resolveCaller({ runId, traceId, capability, input, caller }) {
    const url = `${config.backendInternalBaseUrl.replace(/\/+$/, "")}/api/v1/internal/gateway/resolve-caller`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Gateway-Token": config.gatewayInternalToken,
        },
        signal: controller.signal,
        body: JSON.stringify({ runId, traceId, capability, input, caller }),
      });
    } catch (e) {
      throw new UpstreamError("INTERNAL_ERROR", `resolve-caller 不可达：${e.message}`);
    } finally {
      clearTimeout(timer);
    }
    let body = {};
    try {
      body = await response.json();
    } catch {
      body = {};
    }
    if (!response.ok || body.code !== 0) {
      const reason = (body.data && body.data.reason) || body.message || `HTTP ${response.status}`;
      throw new UpstreamError(
        [400, 403, 422].includes(response.status) ? "INVALID_ARGUMENT" : "INTERNAL_ERROR",
        `caller 路由失败：${reason}`,
      );
    }
    log("info", "gateway_caller_resolved", {
      runId, traceId, mode: body.data?.mode, agentNo: body.data?.agentNo, userId: body.data?.userId,
    });
    return body.data || {};
  }

  return { resolveCaller };
}

module.exports = { createResolverClient };
