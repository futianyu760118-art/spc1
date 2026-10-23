"use strict";

const crypto = require("node:crypto");

/**
 * 中台 HMAC 签名与 HTTP 客户端 —— 语义对齐 mcp-company-control/mcp_server/upstream_client.py
 * （契约 §11/§12/§13 权威参考）：错误码映射、受限重试、{code,message,data} 信封解包。
 * BASE_URL 含 /api/v1 前缀（与 execution-agent / mcp-company-control 约定一致）。
 */
const config = require("../config");

const RETRYABLE = new Set(["UPSTREAM_TIMEOUT", "UPSTREAM_UNAVAILABLE", "RATE_LIMITED"]);
const MAX_ATTEMPTS = 2;
const RETRY_BACKOFF_MS = 400;

class UpstreamError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40 };

function log(level, event, fields) {
  if (LEVELS[level] < LEVELS[config.logLevel]) return;
  const line = JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields });
  if (level === "error") console.error(line);
  else console.log(line);
}

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

/** HTTP 状态 / 信封 code → 契约 §12 错误码（与 upstream_client._map_status 一致，另补 504） */
function mapCode(status) {
  if (status === 400 || status === 422) return "INVALID_ARGUMENT";
  if (status === 401) return "UNAUTHORIZED";
  if (status === 403) return "FORBIDDEN";
  if (status === 404) return "NOT_FOUND";
  if (status === 429) return "RATE_LIMITED";
  if (status === 504) return "UPSTREAM_TIMEOUT";
  if (status >= 500) return "UPSTREAM_UNAVAILABLE";
  return "INTERNAL_ERROR";
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

async function fetchOnce(url, init, timeoutMs, signal) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  if (signal) signal.addEventListener("abort", () => controller.abort(), { once: true });
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
  }
}

/** GET 签名请求（查询用）：受限重试 UPSTREAM_TIMEOUT/UPSTREAM_UNAVAILABLE/RATE_LIMITED 各 1 次。 */
async function signedGet(path, endpointCode, params, { signal } = {}) {
  const queryString = buildQueryString(params);
  const url = `${config.platformBaseUrl}${path}${queryString ? `?${queryString}` : ""}`;
  let lastError;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      const response = await fetchOnce(url, { method: "GET", headers: hmacHeaders(endpointCode, queryString) },
        config.queryTimeoutMs, signal);
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

/** POST 签名请求（推理用）：不自动重试（单次推理可达分钟级，失败快速回报 Hub）。
 * 返回原始 {code,message,data} 信封，由调用方解释（推理需区分 490 取消）。 */
async function signedPostEnvelope(path, endpointCode, body, { signal } = {}) {
  const url = `${config.platformBaseUrl}${path}`;
  let response;
  try {
    response = await fetchOnce(url, {
      method: "POST",
      headers: hmacHeaders(endpointCode, ""),
      body: JSON.stringify(body),
    }, config.reasoningTimeoutMs, signal);
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

module.exports = { log, UpstreamError, mapCode, signedGet, signedPostEnvelope };
