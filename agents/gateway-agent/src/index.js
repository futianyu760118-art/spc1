"use strict";

const {
  HubConnection, startHealthServer, createLogger, createLocalRunHandler, readJsonBody,
} = require("@spc/execution-agent-runtime");
const { buildConfigs } = require("./config");
const { buildAdapters, ADAPTER_BY_CAPABILITY } = require("./adapters");
const { createResolverClient } = require("./resolver-client");
const { createHubClient } = require("./hub-client");

async function main() {
  const { gateway, query, reasoning } = buildConfigs();
  // 网关不参与 query/reasoning 的 DB 配置版本对比，避免状态页误报 pending restart
  gateway.configVersion = null;
  const log = createLogger(() => gateway.logLevel);
  const adapters = await buildAdapters({ query, reasoning, log });
  const resolver = createResolverClient({ config: gateway, log });
  const hub = createHubClient({ config: gateway, log });
  const capabilities = [adapters.query.capability, adapters.reasoning.capability];

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
        throw new Error("resolve-caller 未返回 actorToken，拒绝按系统级执行");
      }
      run.actorToken = resolved.mode === "user" ? resolved.actorToken : null;
      return adapters[ADAPTER_BY_CAPABILITY[run.capability]].invoke(run, input);
    },
    onRecall: (runId) => {
      for (const adapter of Object.values(adapters)) {
        if (adapter.cancel) adapter.cancel(runId);
      }
    },
  };

  const connection = new HubConnection({ config: gateway, log, handlers });

  const localAdapter = {
    invoke: (run, input) => adapters[ADAPTER_BY_CAPABILITY[run.capability]].invoke(run, input),
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
    capabilities,
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
