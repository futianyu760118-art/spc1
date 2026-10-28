"use strict";

const {
  HubConnection, startHealthServer, createLogger, createLocalRunHandler, readJsonBody,
  UpstreamError, ERROR_CODES, splitOutcome,
} = require("@spc/execution-agent-runtime");
const { buildConfigs } = require("./config");
const { buildAdapters } = require("./adapters");
const { buildAgentRegistry, attachResultMetadata } = require("./agent-registry");
const { createResolverClient } = require("./resolver-client");
const { createHubClient } = require("./hub-client");

async function main() {
  const { gateway, query, reasoning, orderWrite } = buildConfigs();
  // 网关不参与 query/reasoning 的 DB 配置版本对比，避免状态页误报 pending restart
  gateway.configVersion = null;
  const log = createLogger(() => gateway.logLevel);
  const adapters = await buildAdapters({ query, reasoning, orderWrite, log });
  const registry = buildAgentRegistry({
    queryAdapter: adapters.query,
    reasoningAdapter: adapters.reasoning,
    orderWriteAdapter: adapters.orderWrite,
    log,
  });
  const capabilities = [
    adapters.query.capability,
    adapters.reasoning.capability,
    adapters.orderWrite.capability,
  ];
  const localCapabilities = capabilities.filter(
    (capability) => capability.name !== adapters.orderWrite.capability.name,
  );
  const resolver = createResolverClient({ config: gateway, log });
  const hub = createHubClient({ config: gateway, log });

  async function invokeAgent(run, input) {
    const resolution = registry.resolve({
      capability: run.capability,
      input,
      targetAgentRef: run.targetAgentRef,
    });
    if (!resolution.agent) {
      const message =
        resolution.error === ERROR_CODES.TARGET_AGENT_UNAVAILABLE
          ? `target_agent_ref 不可用：${run.targetAgentRef || ""}`
          : resolution.error === ERROR_CODES.INTERNAL_ERROR
            ? "内部 Agent 路由存在歧义"
            : resolution.error === ERROR_CODES.CAPABILITY_UNSUPPORTED
              ? `不支持的操作：capability=${run.capability}`
              : `没有可处理该请求的内部 Agent：capability=${run.capability}`;
      throw new UpstreamError(resolution.error, message);
    }
    const agent = resolution.agent;
    log("info", "agent_resolved", {
      runId: run.runId,
      capability: run.capability,
      agentId: agent.agentId,
      requestId: run.requestId,
      targetAgentRef: run.targetAgentRef,
    });
    try {
      const outcome = await agent.invoke(run, input);
      if (outcome === null || outcome === undefined) {
        log("info", "agent_cancelled", { runId: run.runId, agentId: agent.agentId });
        return outcome;
      }
      const { result, usage } = splitOutcome(outcome);
      const withMeta = attachResultMetadata(agent, run, result);
      log("info", "agent_completed", {
        runId: run.runId,
        agentId: agent.agentId,
        requestId: run.requestId,
        hasUsage: usage !== undefined,
      });
      return usage !== undefined ? { result: withMeta, usage } : withMeta;
    } catch (e) {
      log("warn", "agent_failed", {
        runId: run.runId,
        agentId: agent.agentId,
        code: e && e.code,
        message: e && e.message ? e.message : String(e),
      });
      throw e;
    }
  }

  const handlers = {
    capabilities,
    onDispatch: async (run, input) => {
      const resolved = await resolver.resolveCaller({
        runId: run.runId,
        traceId: run.traceId,
        capability: run.capability,
        input,
        caller: run.caller,
      });
      if (resolved.mode === "user" && !resolved.actorToken) {
        throw new UpstreamError(
          ERROR_CODES.INTERNAL_ERROR,
          "resolve-caller 未返回 actorToken，拒绝按系统级执行",
        );
      }
      run.actorToken = resolved.mode === "user" ? resolved.actorToken : null;
      return invokeAgent(run, input);
    },
    onRecall: (runId) => registry.cancel(runId),
  };

  const connection = new HubConnection({ config: gateway, log, handlers });

  const localAdapter = {
    invoke: (run, input) => invokeAgent(run, input),
  };
  const onLocalRun = createLocalRunHandler(localAdapter, connection, log);

  const hubRoutes = [
    {
      method: "POST",
      match: (path) => path === "/internal/hub/borrow-orders",
      handle: (body) => hub.postBorrowOrder(body),
    },
    {
      method: "GET",
      match: (path) => path.startsWith("/internal/hub/borrow-orders/"),
      handle: (body, path) => hub.getBorrowOrder(decodeURIComponent(path.split("/").pop())),
    },
    {
      method: "GET",
      match: (path) => path === "/internal/hub/capability-invocations",
      handle: () => hub.getCatalog(),
    },
    {
      method: "POST",
      match: (path) => path === "/internal/hub/assistant-events",
      handle: (body) => hub.postAssistantEvent(body),
    },
  ];

  async function onHubProxy(req, res, pathname, send) {
    const route = hubRoutes.find((item) => item.method === req.method && item.match(pathname));
    if (!route) {
      send(404, { status: "not_found" });
      return;
    }
    let body = {};
    try {
      body = await readJsonBody(req);
    } catch (e) {
      send(400, { status: e.message });
      return;
    }
    const result = await route.handle(body, pathname);
    send(result.status, result.body || { message: result.text });
  }

  const healthServer = startHealthServer({
    config: gateway,
    log,
    connection,
    capabilities: localCapabilities,
    agentKey: gateway.agentKey,
    onLocalRun,
    onHubProxy,
  });

  connection.start();
  log("info", "gateway_starting", {
    agentId: gateway.agentId,
    hub: gateway.wsUrl,
    capabilities: capabilities.map((c) => c.name),
  });

  const shutdown = () => {
    connection.stop();
    if (healthServer) healthServer.close();
    setTimeout(() => process.exit(0), 200).unref();
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((e) => {
  console.error(JSON.stringify({ level: "error", event: "gateway_start_failed", message: e.message }));
  process.exit(1);
});
