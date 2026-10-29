"use strict";

const { UpstreamError, ERROR_CODES } = require("@spc/execution-agent-runtime");

function createResolverClient({ config, log }) {
  async function resolveCaller({ runId, traceId, capability, input, caller }) {
    const url = `${config.backendInternalBaseUrl.replace(/\/+$/, "")}/api/v1/internal/gateway/resolve-caller`;
    const controller = new AbortController();
    const timeoutMs = config.resolverTimeoutMs || 30000;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
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
      const code =
        timedOut || e.name === "AbortError"
          ? ERROR_CODES.UPSTREAM_TIMEOUT
          : ERROR_CODES.UPSTREAM_UNAVAILABLE;
      throw new UpstreamError(
        code,
        `resolve-caller ${timedOut ? "超时" : "不可达"}：${e.message}`,
      );
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
      const code =
        reason === ERROR_CODES.AGENT_NOT_FOUND
          ? ERROR_CODES.AGENT_NOT_FOUND
          : [400, 403, 422].includes(response.status)
            ? ERROR_CODES.INVALID_ARGUMENT
            : response.status === 504
              ? ERROR_CODES.UPSTREAM_TIMEOUT
              : response.status >= 500
                ? ERROR_CODES.UPSTREAM_UNAVAILABLE
                : ERROR_CODES.INTERNAL_ERROR;
      throw new UpstreamError(code, `caller 路由失败：${reason}`);
    }
    log("info", "gateway_caller_resolved", {
      runId, traceId, mode: body.data?.mode, agentNo: body.data?.agentNo, userId: body.data?.userId,
    });
    return body.data || {};
  }

  return { resolveCaller };
}

module.exports = { createResolverClient };
