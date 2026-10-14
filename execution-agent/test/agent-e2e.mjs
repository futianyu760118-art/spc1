import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startMockHub, waitUntil } from './mock-hub.mjs';

const AGENT_DIR = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const AGENT_ENTRY = path.join(AGENT_DIR, 'src', 'agent.js');
const FAKE_QUERY = path.join(AGENT_DIR, 'test', 'fake-query.mjs');
const CAP = 'query_control_platform';

const results = [];

function spawnAgent(hubUrl, extraEnv = {}, { ipc = false } = {}) {
  const proc = spawn(process.execPath, [AGENT_ENTRY], {
    env: {
      ...process.env,
      EXECUTION_WS_URL: hubUrl,
      EXECUTION_PLANE_TOKEN: 'test-token',
      PYTHON_BIN: process.execPath,
      QUERY_SCRIPT: FAKE_QUERY,
      QUERY_TIMEOUT_MS: '1500',
      HEALTH_CHECK_PORT: '0',
      LOG_LEVEL: 'debug',
      ...extraEnv,
    },
    stdio: ['ignore', 'pipe', 'pipe', ...(ipc ? ['ipc'] : [])],
  });
  const stdoutLines = [];
  proc.stdout.setEncoding('utf8');
  proc.stdout.on('data', (chunk) => stdoutLines.push(...chunk.split('\n').filter(Boolean)));
  return { proc, stdoutLines };
}

async function stopAgent(agent) {
  if (agent.proc.exitCode !== null) return agent.proc.exitCode;
  agent.proc.kill('SIGTERM');
  return new Promise((resolve) => {
    const timer = setTimeout(() => agent.proc.kill('SIGKILL'), 3000);
    agent.proc.on('exit', (code) => {
      clearTimeout(timer);
      resolve(code);
    });
  });
}

const ofType = (list, type) => list.filter((m) => m.type === type);
const dispatchInput = (path, params = {}) => ({ path, params });

async function runScenario(name, fn) {
  const ctx = { agents: [], hub: null };
  try {
    await fn(ctx);
    results.push({ name, pass: true });
    console.log(`PASS ${name}`);
  } catch (err) {
    results.push({ name, pass: false, error: err.message });
    console.log(`FAIL ${name}: ${err.message}`);
    if (ctx.hub) console.log('  received:', JSON.stringify(ctx.hub.received.slice(-8)));
  } finally {
    for (const agent of ctx.agents) await stopAgent(agent);
    if (ctx.hub) await ctx.hub.close().catch(() => {});
  }
}

async function main() {
  await runScenario('register_and_heartbeat', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    const register = await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    if (register.agentId !== 'runtime-execution-query') throw new Error(`agentId=${register.agentId}`);
    if (!register.capabilities?.some((c) => c.name === CAP)) throw new Error('capabilities 缺 query_control_platform');
    await waitUntil(() => ofType(ctx.hub.received, 'heartbeat').filter((m) => m.status === 'idle').length >= 2);
  });

  await runScenario('dispatch_ok', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r1', capability: CAP, input: dispatchInput('/external/orders/list', { keyword: 'SO-1' }) });
    await waitUntil(() => ofType(ctx.hub.received, 'run_update')[0]);
    const complete = await waitUntil(() => ofType(ctx.hub.received, 'run_complete')[0]);
    if (complete.result?.path !== '/external/orders/list') throw new Error('result.path 不符');
  });

  await runScenario('working_heartbeat_during_slow_run', async (ctx) => {
    ctx.hub = startMockHub({ heartbeatIntervalMs: 100 });
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r2', capability: CAP, input: dispatchInput('/common/ping', { __fake_mode: 'slow' }) });
    const hb = await waitUntil(() =>
      ofType(ctx.hub.received, 'heartbeat').find((m) => m.status === 'working' && m.currentRunId === 'r2')
    );
    if (!hb) throw new Error('未见 working 心跳');
    await waitUntil(() => ofType(ctx.hub.received, 'run_complete')[0]);
    await waitUntil(() => ofType(ctx.hub.received, 'heartbeat').some((m) => m.status === 'idle'));
  });

  await runScenario('dispatch_upstream_fail', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r3', capability: CAP, input: dispatchInput('/common/ping', { __fake_mode: 'fail' }) });
    const failed = await waitUntil(() => ofType(ctx.hub.received, 'run_failed')[0]);
    if (failed.error?.code !== 'UPSTREAM_UNAVAILABLE') throw new Error(`code=${failed.error?.code}`);
  });

  await runScenario('dispatch_invalid_path', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r4', capability: CAP, input: dispatchInput('/external/nope') });
    const failed = await waitUntil(() => ofType(ctx.hub.received, 'run_failed')[0]);
    if (failed.error?.code !== 'INVALID_ARGUMENT') throw new Error(`code=${failed.error?.code}`);
    if (ofType(ctx.hub.received, 'run_update').length !== 0) throw new Error('不应发 run_update');
  });

  await runScenario('dispatch_unknown_capability', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r5', capability: 'write_something', input: dispatchInput('/common/ping') });
    const failed = await waitUntil(() => ofType(ctx.hub.received, 'run_failed')[0]);
    if (failed.error?.code !== 'INVALID_ARGUMENT') throw new Error(`code=${failed.error?.code}`);
  });

  await runScenario('busy_reject_and_recall_no_report', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r6a', capability: CAP, input: dispatchInput('/common/ping', { __fake_mode: 'hang' }) });
    await waitUntil(() => ofType(ctx.hub.received, 'run_update')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r6b', capability: CAP, input: dispatchInput('/common/ping') });
    const busy = await waitUntil(() => ofType(ctx.hub.received, 'run_failed').find((m) => m.runId === 'r6b'));
    if (busy.error?.code !== 'INTERNAL_ERROR') throw new Error(`code=${busy.error?.code}`);
    ctx.hub.send({ type: 'recall', runId: 'r6a' });
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (ofType(ctx.hub.received, 'run_complete').length !== 0) throw new Error('recall 后不应有 run_complete');
    if (ofType(ctx.hub.received, 'run_failed').some((m) => m.runId === 'r6a')) throw new Error('recall 后不应有 r6a 的 run_failed');
    await waitUntil(() => ofType(ctx.hub.received, 'heartbeat').some((m) => m.status === 'idle'));
  });

  await runScenario('dispatch_crash_maps_internal_error', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r7', capability: CAP, input: dispatchInput('/common/ping', { __fake_mode: 'crash' }) });
    const failed = await waitUntil(() => ofType(ctx.hub.received, 'run_failed')[0]);
    if (failed.error?.code !== 'INTERNAL_ERROR') throw new Error(`code=${failed.error?.code}`);
  });

  await runScenario('dispatch_timeout', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`, { QUERY_TIMEOUT_MS: '400' }));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    ctx.hub.send({ type: 'dispatch', runId: 'r8', capability: CAP, input: dispatchInput('/common/ping', { __fake_mode: 'hang' }) });
    const failed = await waitUntil(() => ofType(ctx.hub.received, 'run_failed')[0], { timeoutMs: 5000 });
    if (failed.error?.code !== 'UPSTREAM_TIMEOUT') throw new Error(`code=${failed.error?.code}`);
  });

  await runScenario('reconnect_and_reregister', async (ctx) => {
    const port = 39000 + Math.floor(Math.random() * 900);
    ctx.hub = startMockHub({ port });
    await ctx.hub.ready;
    ctx.agents.push(spawnAgent(`ws://127.0.0.1:${port}/execution-agent`));
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    await ctx.hub.close();
    await new Promise((resolve) => setTimeout(resolve, 300));
    const hub2 = startMockHub({ port });
    ctx.hub = hub2;
    await hub2.ready;
    await waitUntil(() => ofType(hub2.received, 'register')[0], { timeoutMs: 12000 });
  });

  await runScenario('graceful_exit_zero', async (ctx) => {
    ctx.hub = startMockHub();
    await ctx.hub.ready;
    const agent = spawnAgent(`ws://127.0.0.1:${ctx.hub.port}/execution-agent`, {}, { ipc: true });
    ctx.agents.push(agent);
    await waitUntil(() => ofType(ctx.hub.received, 'register')[0]);
    const code = await new Promise((resolve) => {
      const timer = setTimeout(() => resolve('timeout'), 5000);
      agent.proc.on('exit', (exitCode) => {
        clearTimeout(timer);
        resolve(exitCode);
      });
      agent.proc.send({ type: 'shutdown' });
    });
    ctx.agents = ctx.agents.filter((a) => a !== agent);
    if (code !== 0) throw new Error(`exit=${code}`);
  });

  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} scenarios passed`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((err) => {
  console.error('E2E_RUNNER_ERROR', err);
  process.exit(1);
});
