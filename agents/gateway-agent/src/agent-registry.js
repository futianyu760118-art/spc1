"use strict";

const { ERROR_CODES } = require("@spc/execution-agent-runtime");
const WRITE_OPERATIONS_REGISTRY = require("../../shared/order-write-operations.json");

const REASONING_AGENTS = Object.freeze([
  {
    agentId: "spc-agent-order-risk",
    agentName: "订单风险分析 Agent",
    role: "order_risk",
    taskTypes: ["order_delivery_analysis"],
  },
  {
    agentId: "spc-agent-kitting-risk",
    agentName: "齐套风险分析 Agent",
    role: "kitting_risk",
    taskTypes: ["material_kitting_analysis"],
  },
  {
    agentId: "spc-agent-quality-risk",
    agentName: "质量风险分析 Agent",
    role: "quality_risk",
    taskTypes: ["quality_analysis"],
  },
  {
    agentId: "spc-agent-production-risk",
    agentName: "生产风险分析 Agent",
    role: "production_risk",
    taskTypes: ["production_analysis"],
  },
]);

const WRITE_AGENT = Object.freeze({
  agentId: "spc-agent-order-write",
  agentName: "订单写操作 Agent",
  role: "order_write",
  operations: WRITE_OPERATIONS_REGISTRY.operations.map((operation) => operation.name),
});

function taskTypeOf(input) {
  return input && typeof input === "object" && typeof input.task_type === "string"
    ? input.task_type
    : "";
}

function operationOf(input) {
  return input && typeof input === "object" && typeof input.operation === "string"
    ? input.operation
    : "";
}

function matchesInput(agent, input) {
  if (Array.isArray(agent.operations) && agent.operations.length) {
    const operation = operationOf(input);
    return operation !== "" && agent.operations.includes(operation);
  }
  if (!agent.taskTypes || agent.taskTypes.length === 0) return true;
  return agent.taskTypes.includes(taskTypeOf(input));
}

function validateAgents(agents) {
  const ids = new Set();
  const routes = new Set();
  for (const agent of agents) {
    if (!agent.agentId || !agent.capability) {
      throw new Error("agent 注册项缺少 agentId/capability");
    }
    if (ids.has(agent.agentId)) throw new Error(`重复 agentId: ${agent.agentId}`);
    ids.add(agent.agentId);

    const keys = [];
    if (Array.isArray(agent.operations) && agent.operations.length) {
      keys.push(
        ...agent.operations.map(
          (operation) => `${agent.capability}::operation:${operation}`,
        ),
      );
    } else {
      const taskTypes =
        Array.isArray(agent.taskTypes) && agent.taskTypes.length ? agent.taskTypes : ["*"];
      keys.push(
        ...taskTypes.map((taskType) => `${agent.capability}::task_type:${taskType}`),
      );
    }
    for (const key of keys) {
      if (routes.has(key)) throw new Error(`重复 Agent 路由: ${key}`);
      routes.add(key);
    }
  }
}

function buildAgentRegistry({
  queryAdapter,
  reasoningAdapter,
  orderWriteAdapter,
  log = () => {},
}) {
  const queryCapability = queryAdapter.capability && queryAdapter.capability.name;
  const reasoningCapability = reasoningAdapter.capability && reasoningAdapter.capability.name;
  const writeCapability = orderWriteAdapter.capability && orderWriteAdapter.capability.name;
  if (!queryCapability || !reasoningCapability || !writeCapability) {
    throw new Error("agent 注册表缺少 adapter capability");
  }
  const noMatchErrors = new Map([
    [reasoningCapability, ERROR_CODES.AGENT_NOT_FOUND],
    [writeCapability, ERROR_CODES.CAPABILITY_UNSUPPORTED],
  ]);
  const agents = [
    {
      agentId: "spc-agent-query",
      agentName: "中台查询智能体",
      role: "query",
      capability: queryCapability,
      taskTypes: [],
      emitHandledBy: false,
      echoRequestId: false,
      invoke: queryAdapter.invoke,
      cancel: queryAdapter.cancel,
    },
    ...REASONING_AGENTS.map((spec) => ({
      ...spec,
      capability: reasoningCapability,
      emitHandledBy: true,
      echoRequestId: true,
      invoke: reasoningAdapter.invoke,
      cancel: reasoningAdapter.cancel,
    })),
    {
      ...WRITE_AGENT,
      capability: writeCapability,
      emitHandledBy: true,
      echoRequestId: true,
      invoke: orderWriteAdapter.invoke,
      cancel: orderWriteAdapter.cancel,
    },
  ];

  validateAgents(agents);
  const byId = new Map(agents.map((agent) => [agent.agentId, agent]));

  function resolve({ capability, input, targetAgentRef }) {
    if (targetAgentRef) {
      const agent = byId.get(targetAgentRef);
      if (!agent || agent.capability !== capability || !matchesInput(agent, input)) {
        return { agent: null, error: ERROR_CODES.TARGET_AGENT_UNAVAILABLE };
      }
      return { agent, error: null };
    }
    const candidates = agents.filter(
      (agent) => agent.capability === capability && matchesInput(agent, input),
    );
    if (candidates.length === 1) return { agent: candidates[0], error: null };
    if (candidates.length === 0) {
      return {
        agent: null,
        error: noMatchErrors.get(capability) || ERROR_CODES.AGENT_NOT_FOUND,
      };
    }
    log("error", "agent_registry_ambiguous", {
      capability,
      agentIds: candidates.map((agent) => agent.agentId),
    });
    return { agent: null, error: ERROR_CODES.INTERNAL_ERROR };
  }

  function cancel(runId) {
    const cancelers = new Set(
      agents
        .map((agent) => agent.cancel)
        .filter((cancelFn) => typeof cancelFn === "function"),
    );
    for (const cancelFn of cancelers) {
      Promise.resolve()
        .then(() => cancelFn(runId))
        .catch((e) =>
          log("warn", "agent_cancel_failed", {
            runId,
            code: e && e.code,
            message: e && e.message ? e.message : String(e),
          }),
        );
    }
  }

  return { agents, byId, resolve, cancel };
}

function buildHandledBy(agent, result) {
  if (!agent || !agent.emitHandledBy) return null;
  if (!result || typeof result !== "object" || Array.isArray(result)) return null;
  const handledBy = {
    agentId: agent.agentId,
    agentName: agent.agentName,
    role: agent.role,
  };
  const model = result.llm && typeof result.llm === "object" ? result.llm.model : null;
  if (model) handledBy.model = model;
  return handledBy;
}

function attachResultMetadata(agent, run, result) {
  if (!agent || !result || typeof result !== "object" || Array.isArray(result)) return result;
  const metadata = {};
  if (agent.echoRequestId && run.requestId) {
    metadata.request_id = run.requestId;
  }
  const handledBy = buildHandledBy(agent, result);
  if (handledBy) metadata.handled_by = handledBy;
  return Object.keys(metadata).length ? { ...result, ...metadata } : result;
}

module.exports = {
  REASONING_AGENTS,
  WRITE_AGENT,
  buildAgentRegistry,
  buildHandledBy,
  attachResultMetadata,
  validateAgents,
};
