"use strict";

const { UpstreamError } = require("@spc/execution-agent-runtime");

// path → endpoint_code 映射三处同步：本文件 / upstream_client._ENDPOINT_CODES / SPC 对外接口注册表
const PATH_ENDPOINT_CODES = Object.freeze({
  "/common/ping": "int:health.ping",
  "/external/orders/list": "orders.list",
  "/external/order-details/list": "order_details.list",
  "/external/boms/tree": "boms.tree",
  "/external/materials/list": "materials.list",
  "/external/suppliers/list": "suppliers.list",
  "/external/material-kitting/results": "kitting.results",
  "/external/material-kitting/shortages": "kitting.shortages",
  "/external/material-kitting/demands": "kitting.demands",
  "/external/inventory/availability": "inventory.availability",
  "/external/material-supplies/list": "material.supplies",
  "/external/quality-issues/list": "quality_issues.list",
  "/external/quality-trace/list": "quality_trace.list",
  "/external/production/work-orders/list": "production.work_orders.list",
  "/external/production/operations/list": "production.operations.list",
  "/external/production/order-links/list": "production.order_links.list",
  "/external/production/reports/list": "production.reports.list",
  "/external/production/capacity/list": "production.capacity.list",
});

const inputSchema = Object.freeze({
  type: "object",
  properties: {
    path: { type: "string", enum: Object.keys(PATH_ENDPOINT_CODES) },
    params: { type: "object", description: "查询参数（分页/筛选），缺省为空对象" },
  },
  required: ["path"],
});

const outputSchema = Object.freeze({
  type: "object",
  description: "中台 {code,message,data} 信封的 data（逐端点结构不同）",
});

function summarizeResult(data) {
  if (Array.isArray(data)) return `返回 ${data.length} 条`;
  if (data && Array.isArray(data.items)) return `返回 ${data.items.length} 条`;
  return "查询完成";
}

function createAdapter({ config, http, log }) {
  const capability = {
    name: "query_control_platform",
    description: "中台只读查询（契约 §4.2 冻结白名单）",
    readOnly: true,
    constraints: { readOnly: true },
    inputSchema,
    outputSchema,
  };

  async function invoke(run, input) {
    const path = input && input.path;
    const endpointCode = PATH_ENDPOINT_CODES[path];
    if (!endpointCode) {
      throw new UpstreamError("INVALID_ARGUMENT", `path 不在白名单（契约 §4.2）：${path}`);
    }
    const params = input.params ?? {};
    if (typeof params !== "object" || params === null || Array.isArray(params)) {
      throw new UpstreamError("INVALID_ARGUMENT", "params 必须是对象");
    }
    const report = run.report;
    const startedAt = new Date().toISOString();
    report("step_started", "查询中台接口", "started", `path=${path}`, { path }, { startedAt });
    log("info", "query_started", { path });
    try {
      const headers = run.actorToken ? { "X-Actor-Token": run.actorToken } : {};
      const data = await http.signedGet(path, endpointCode, params, {
        signal: run.controller.signal,
        timeoutMs: config.queryTimeoutMs,
        headers,
      });
      report("step_completed", "查询中台接口", "completed", summarizeResult(data), { path }, { startedAt });
      log("info", "query_ok", { path });
      return data;
    } catch (e) {
      report("error", "查询中台接口", "failed", e.message, { path, code: e.code }, { startedAt });
      throw e;
    }
  }

  return { capability, invoke };
}

module.exports = { createAdapter, PATH_ENDPOINT_CODES, inputSchema, outputSchema };
