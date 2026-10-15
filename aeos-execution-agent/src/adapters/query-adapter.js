"use strict";

const { log, UpstreamError, signedGet } = require("../lib/http-client");

/**
 * 查询适配器（query_control_platform）。
 * 输入契约与 execution-agent / mcp-company-control 一致：{ path, params }，
 * path 白名单为执行面契约 §4.2 冻结值（18 路径 + /common/ping）。
 * 签名用 path → endpoint_code 映射三处同步维护：
 * 本文件 / upstream_client._ENDPOINT_CODES / SPC 对外接口注册表。
 */
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

/** 能力自描述（管理面 127b013 起 register 必带）：输入 {path, params}，输出为中台信封 data（逐端点形状不同，仅约束为对象）。 */
const inputSchema = Object.freeze({
  type: "object",
  properties: {
    path: { type: "string", enum: Object.keys(PATH_ENDPOINT_CODES) },
    params: { type: "object", description: "查询参数（分页/筛选），缺省为空对象" },
  },
  required: ["path"],
});

const outputSchema = Object.freeze({ type: "object", description: "中台 {code,message,data} 信封的 data（逐端点结构不同）" });

function invoke(input) {
  const path = input && input.path;
  const endpointCode = PATH_ENDPOINT_CODES[path];
  if (!endpointCode) {
    throw new UpstreamError("INVALID_ARGUMENT", `path 不在白名单（契约 §4.2）：${path}`);
  }
  const params = input.params ?? {};
  if (typeof params !== "object" || params === null || Array.isArray(params)) {
    throw new UpstreamError("INVALID_ARGUMENT", "params 必须是对象");
  }
  log("info", "query_started", { path });
  return signedGet(path, endpointCode, params).then((data) => {
    log("info", "query_ok", { path });
    return data;
  });
}

module.exports = { invoke, PATH_ENDPOINT_CODES, inputSchema, outputSchema };
