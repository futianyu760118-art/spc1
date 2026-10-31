"use strict";

const crypto = require("node:crypto");
const { ERROR_CODES } = require("./error-codes");

const RETRYABLE = new Set([
  ERROR_CODES.UPSTREAM_TIMEOUT,
  ERROR_CODES.UPSTREAM_UNAVAILABLE,
  ERROR_CODES.RATE_LIMITED,
]);
const MAX_ATTEMPTS = 2;
const RETRY_BACKOFF_MS = 400;

class UpstreamError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function mapCode(status) {
  if (status === 400 || status === 422) return ERROR_CODES.INVALID_ARGUMENT;
  if (status === 401) return ERROR_CODES.UNAUTHORIZED;
  if (status === 403) return ERROR_CODES.FORBIDDEN;
  if (status === 404) return ERROR_CODES.NOT_FOUND;
  if (status === 409) return ERROR_CODES.AGENT_BUSY;
  if (status === 429) return ERROR_CODES.RATE_LIMITED;
  if (status === 504) return ERROR_CODES.UPSTREAM_TIMEOUT;
  if (status >= 500) return ERROR_CODES.UPSTREAM_UNAVAILABLE;
  return ERROR_CODES.INTERNAL_ERROR;
}

function unwrapEnvelope(body) {
  if (body && typeof body === "object" && "code" in body) {
    if (body.code !== 0 && body.code !== null) {
      const code = typeof body.code === "number" ? mapCode(body.code) : "INTERNAL_ERROR";
      throw new UpstreamError(code, String(body.message || `中台返回业务错误 code=${body.code}`));
    }
    return body.data;
  }
  return body;
}

function buildQueryString(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === undefined || value === null || value === "") continue;
    search.append(key, String(value));
  }
  return search.toString();
}

function createHttpClient(config, log) {
  function hmacHeaders(endpointCode, queryString) {
    const timestamp = String(Math.floor(Date.now() / 1000));
    const stringToSign = `${timestamp}${config.appKey}${endpointCode}${queryString}`;
    const signature = crypto
      .createHmac("sha256", config.appSecret)
      .update(stringToSign, "utf8")
      .digest("hex");
    return {
      "X-App-Key": config.appKey,
      "X-Timestamp": timestamp,
      "X-Signature": signature,
      "Content-Type": "application/json",
    };
  }

  async function fetchOnce(url, init, timeoutMs, signal) {
    if (signal && signal.aborted) {
      throw new UpstreamError("ABORTED", "请求已中止（召回/断线）");
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const onExternalAbort = () => controller.abort();
    if (signal) signal.addEventListener("abort", onExternalAbort, { once: true });
    try {
      return await fetch(url, { ...init, signal: controller.signal });
    } catch (e) {
      if (String(e && e.name) === "AbortError" && signal && signal.aborted) {
        throw new UpstreamError("ABORTED", "请求已中止（召回/断线）");
      }
      if (String(e && e.name) === "AbortError") {
        throw new UpstreamError("UPSTREAM_TIMEOUT", `中台响应超时（>${timeoutMs}ms）`);
      }
      throw new UpstreamError("UPSTREAM_UNAVAILABLE", `中台不可达：${e.message}`);
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", onExternalAbort);
    }
  }

  async function signedGet(path, endpointCode, params, { signal, timeoutMs = 15000, headers = {} } = {}) {
    const queryString = buildQueryString(params);
    const url = `${config.platformBaseUrl}${path}${queryString ? `?${queryString}` : ""}`;
    let lastError;
    for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
      try {
        const response = await fetchOnce(
          url,
          { method: "GET", headers: { ...hmacHeaders(endpointCode, queryString), ...headers } },
          timeoutMs,
          signal,
        );
        if (response.status === 200) return unwrapEnvelope(await response.json());
        lastError = new UpstreamError(mapCode(response.status), `中台端点 ${path} 返回 HTTP ${response.status}`);
      } catch (e) {
        if (e instanceof UpstreamError) lastError = e;
        else lastError = new UpstreamError("INTERNAL_ERROR", String(e.message || e));
      }
      if (attempt < MAX_ATTEMPTS && RETRYABLE.has(lastError.code)) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_BACKOFF_MS));
        continue;
      }
      break;
    }
    log("warn", "upstream_failed", { path, code: lastError.code, message: lastError.message });
    throw lastError;
  }

  async function signedSendEnvelope(method, path, endpointCode, body, { signal, timeoutMs = 180000, headers = {} } = {}) {
    const url = `${config.platformBaseUrl}${path}`;
    let response;
    try {
      response = await fetchOnce(
        url,
        {
          method,
          headers: { ...hmacHeaders(endpointCode, ""), ...headers },
          body: JSON.stringify(body),
        },
        timeoutMs,
        signal,
      );
    } catch (e) {
      if (e instanceof UpstreamError) throw e;
      throw new UpstreamError("INTERNAL_ERROR", String(e.message || e));
    }
    if (response.status !== 200) {
      throw new UpstreamError(mapCode(response.status), `中台端点 ${path} 返回 HTTP ${response.status}`);
    }
    try {
      return await response.json();
    } catch {
      throw new UpstreamError("UPSTREAM_UNAVAILABLE", "中台响应非 JSON");
    }
  }

  function signedPostEnvelope(path, endpointCode, body, opts) {
    return signedSendEnvelope("POST", path, endpointCode, body, opts);
  }

  return { signedGet, signedPostEnvelope, signedSendEnvelope };
}

module.exports = { createHttpClient, UpstreamError, mapCode, unwrapEnvelope, buildQueryString };
