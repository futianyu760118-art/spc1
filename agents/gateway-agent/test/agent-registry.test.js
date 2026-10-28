"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  buildAgentRegistry,
  buildHandledBy,
  attachResultMetadata,
  validateAgents,
} = require("../src/agent-registry");

function fakeAdapters() {
  return {
    queryAdapter: {
      capability: { name: "query_control_platform" },
      invoke: async () => ({ ok: true }),
    },
    reasoningAdapter: {
      capability: { name: "reason_control_platform" },
      invoke: async () => ({ result: {}, usage: {} }),
      cancel: () => {},
    },
  };
}

test("resolves each reasoning task type to its stable logical agent", () => {
  const registry = buildAgentRegistry(fakeAdapters());
  const cases = [
    ["order_delivery_analysis", "spc-agent-order-risk", "订单风险分析 Agent", "order_risk"],
    ["material_kitting_analysis", "spc-agent-kitting-risk", "齐套风险分析 Agent", "kitting_risk"],
    ["quality_analysis", "spc-agent-quality-risk", "质量风险分析 Agent", "quality_risk"],
    ["production_analysis", "spc-agent-production-risk", "生产风险分析 Agent", "production_risk"],
  ];
  for (const [taskType, agentId, agentName, role] of cases) {
    const { agent, error } = registry.resolve({
      capability: "reason_control_platform",
      input: { task_type: taskType },
    });
    assert.equal(error, null);
    assert.equal(agent.agentId, agentId);
    assert.equal(agent.agentName, agentName);
    assert.equal(agent.role, role);
  }
});

test("returns AGENT_NOT_FOUND for unknown task types and capabilities", () => {
  const registry = buildAgentRegistry(fakeAdapters());
  assert.equal(
    registry.resolve({
      capability: "reason_control_platform",
      input: { task_type: "unknown" },
    }).error,
    "AGENT_NOT_FOUND",
  );
  assert.equal(
    registry.resolve({ capability: "unknown", input: {} }).error,
    "AGENT_NOT_FOUND",
  );
});

test("routes target_agent_ref only when capability and task type match", () => {
  const registry = buildAgentRegistry(fakeAdapters());
  const ok = registry.resolve({
    capability: "reason_control_platform",
    input: { task_type: "order_delivery_analysis" },
    targetAgentRef: "spc-agent-order-risk",
  });
  assert.equal(ok.error, null);
  assert.equal(ok.agent.agentId, "spc-agent-order-risk");

  const missing = registry.resolve({
    capability: "reason_control_platform",
    input: { task_type: "order_delivery_analysis" },
    targetAgentRef: "spc-agent-missing",
  });
  assert.equal(missing.error, "TARGET_AGENT_UNAVAILABLE");

  const wrongTask = registry.resolve({
    capability: "reason_control_platform",
    input: { task_type: "quality_analysis" },
    targetAgentRef: "spc-agent-order-risk",
  });
  assert.equal(wrongTask.error, "TARGET_AGENT_UNAVAILABLE");

  const wrongCapability = registry.resolve({
    capability: "query_control_platform",
    input: {},
    targetAgentRef: "spc-agent-order-risk",
  });
  assert.equal(wrongCapability.error, "TARGET_AGENT_UNAVAILABLE");
});

test("resolves the query agent without result metadata", () => {
  const registry = buildAgentRegistry(fakeAdapters());
  const { agent, error } = registry.resolve({
    capability: "query_control_platform",
    input: { path: "/external/orders/list" },
  });
  assert.equal(error, null);
  assert.equal(agent.agentId, "spc-agent-query");
  assert.equal(agent.emitHandledBy, false);
  assert.equal(agent.echoRequestId, false);
});

test("buildHandledBy includes model only when present", () => {
  const registry = buildAgentRegistry(fakeAdapters());
  const agent = registry.byId.get("spc-agent-order-risk");
  assert.deepEqual(buildHandledBy(agent, { llm: { model: "deepseek-flash" } }), {
    agentId: "spc-agent-order-risk",
    agentName: "订单风险分析 Agent",
    role: "order_risk",
    model: "deepseek-flash",
  });
  assert.deepEqual(buildHandledBy(agent, { llm: {} }), {
    agentId: "spc-agent-order-risk",
    agentName: "订单风险分析 Agent",
    role: "order_risk",
  });
  assert.equal(buildHandledBy(agent, []), null);
});

test("attachResultMetadata adds request_id and handled_by for reasoning only", () => {
  const registry = buildAgentRegistry(fakeAdapters());
  const reasoning = registry.byId.get("spc-agent-order-risk");
  const result = attachResultMetadata(
    reasoning,
    { requestId: "req-1" },
    { summary: "s", llm: { model: "deepseek-flash" } },
  );
  assert.equal(result.request_id, "req-1");
  assert.equal(result.handled_by.agentId, "spc-agent-order-risk");
  assert.equal(result.handled_by.model, "deepseek-flash");

  const query = registry.byId.get("spc-agent-query");
  const queryResult = { items: [] };
  assert.deepEqual(attachResultMetadata(query, { requestId: "req-1" }, queryResult), queryResult);
});

test("validateAgents rejects duplicate ids and routes", () => {
  const base = {
    agentName: "x",
    role: "x",
    capability: "c",
    taskTypes: ["t"],
    emitHandledBy: false,
    echoRequestId: false,
  };
  assert.throws(
    () => validateAgents([{ ...base, agentId: "a" }, { ...base, agentId: "a" }]),
    /重复 agentId/,
  );
  assert.throws(
    () => validateAgents([{ ...base, agentId: "a" }, { ...base, agentId: "b" }]),
    /重复 Agent 路由/,
  );
});
