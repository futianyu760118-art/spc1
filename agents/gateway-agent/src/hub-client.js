"use strict";

const { normalizeCaller } = require("@spc/execution-agent-runtime");

const CONTRACT_VERSION = "4.0";

function createHubClient({ config, log }) {
  function headers() {
    return {
      "x-aeos-system-id": encodeURIComponent(config.hubSystemId || ""),
      "x-aeos-system-token": config.hubSystemToken || "",
      "X-AEOS-Contract-Version": CONTRACT_VERSION,
      "Content-Type": "application/json",
    };
  }

  function prepareCaller(caller) {
    if (!caller || typeof caller !== "object") return null;
    if (caller.systemId && caller.systemId !== config.hubSystemId) {
      const error = new Error("caller.systemId 与系统令牌声明的 systemId 不一致");
      error.statusCode = 400;
      throw error;
    }
    const normalized = normalizeCaller(caller) || {};
    if (config.hubSystemId) normalized.systemId = config.hubSystemId;
    return Object.keys(normalized).length ? normalized : null;
  }

  async function call(method, path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    let response;
    try {
      response = await fetch(`${config.hubBaseUrl.replace(/\/+$/, "")}${path}`, {
        method,
        headers: headers(),
        signal: controller.signal,
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } finally {
      clearTimeout(timer);
    }
    const text = await response.text();
    let parsed = null;
    try { parsed = text ? JSON.parse(text) : null; } catch { parsed = null; }
    log("info", "hub_proxy_call", { method, path, status: response.status });
    return { status: response.status, body: parsed, text };
  }

  async function postBorrowOrder(payload) {
    let caller;
    try {
      caller = prepareCaller(payload.caller);
    } catch (e) {
      return {
        status: e.statusCode || 400,
        body: { code: "INVALID_ARGUMENT", message: e.message },
        text: e.message,
      };
    }
    const body = { ...payload };
    if (caller) body.caller = caller;
    else delete body.caller;
    return call("POST", "/api/system/borrow-orders", body);
  }

  async function getBorrowOrder(orderId) {
    return call("GET", `/api/system/borrow-orders/${encodeURIComponent(orderId)}`);
  }

  async function getCatalog() {
    return call("GET", "/api/system/capability-invocations");
  }

  async function postAssistantEvent(payload) {
    return call("POST", "/api/system/assistant-events", payload);
  }

  return { postBorrowOrder, getBorrowOrder, getCatalog, postAssistantEvent };
}

module.exports = { createHubClient };
