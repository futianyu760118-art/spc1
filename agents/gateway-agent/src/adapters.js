"use strict";

const { createHttpClient, createRemoteConfig } = require("@spc/execution-agent-runtime");
const { createAdapter: createQueryAdapter } = require("../../query-agent/src/query-adapter");
const { createAdapter: createReasoningAdapter } = require("../../reasoning-agent/src/reasoning-adapter");
const { createAdapter: createOrderWriteAdapter } = require("./order-write-adapter");

async function buildAdapters({ query, reasoning, orderWrite, log }) {
  const queryHttp = createHttpClient(query, log);
  const reasoningHttp = createHttpClient(reasoning, log);
  const orderWriteHttp = createHttpClient(orderWrite, log);

  // 分别按 query/reasoning scope 拉取运行配置；避免 agent=gateway（后端 400）
  await Promise.all([
    createRemoteConfig({
      config: query,
      configMap: { query_timeout_ms: "queryTimeoutMs" },
      http: queryHttp,
      log,
    }).applyRemoteConfigWithRetry(),
    createRemoteConfig({
      config: reasoning,
      configMap: { reasoning_timeout_ms: "reasoningTimeoutMs" },
      http: reasoningHttp,
      log,
    }).applyRemoteConfigWithRetry(),
  ]);

  return {
    query: createQueryAdapter({ config: query, http: queryHttp, log }),
    reasoning: createReasoningAdapter({ config: reasoning, http: reasoningHttp, log }),
    orderWrite: createOrderWriteAdapter({ config: orderWrite, http: orderWriteHttp, log }),
  };
}

module.exports = { buildAdapters };
