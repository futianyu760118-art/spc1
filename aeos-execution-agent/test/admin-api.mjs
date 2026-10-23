// 管理面 + 远程配置拉取集成测试：stub HTTP 服务扮演中台，子进程跑 src/index.js
// 运行：node test/admin-api.mjs
import { spawn } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const AGENT_DIR = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const AGENT_ENTRY = path.join(AGENT_DIR, 'src', 'index.js');
const ADMIN_TOKEN = 'test-token';

function randomHighPort() {
  return 20000 + Math.floor(Math.random() * 20000);
}

function startStubPlatform() {
  let configHits = 0;
  const server = http.createServer((req, res) => {
    const pathname = req.url ? req.url.split('?')[0] : '';
    if (req.method === 'GET' && pathname === '/external/agent/config') {
      configHits += 1;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        code: 0,
        data: { version: 1, config: { agent_name: '远程名' } },
      }));
      return;
    }
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ code: 404, message: `stub 无此路由 ${pathname}` }));
  });
  const ready = new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () => resolve(server.address().port))
  );
  return {
    ready,
    get configHits() {
      return configHits;
    },
    async close() {
      await new Promise((resolve) => server.close(() => resolve()));
    },
  };
}

function spawnAgent({ stubPort, healthPort }) {
  const proc = spawn(process.execPath, [AGENT_ENTRY], {
    env: {
      ...process.env,
      EXECUTION_WS_URL: `ws://127.0.0.1:${stubPort}/execution-agent`,
      EXECUTION_PLANE_TOKEN: 'test-token',
      CONTROL_PLATFORM_BASE_URL: `http://127.0.0.1:${stubPort}`,
      CONTROL_PLATFORM_APP_KEY: 'test-key',
      CONTROL_PLATFORM_APP_SECRET: 'test-secret',
      AGENT_ADMIN_TOKEN: ADMIN_TOKEN,
      HEALTH_CHECK_PORT: String(healthPort),
      LOG_LEVEL: 'info',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const logLines = [];
  proc.stdout.setEncoding('utf8');
  proc.stdout.on('data', (chunk) => logLines.push(...chunk.split('\n').filter(Boolean)));
  proc.stderr.setEncoding('utf8');
  proc.stderr.on('data', (chunk) => logLines.push(...chunk.split('\n').filter(Boolean)));
  return { proc, logLines };
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

function waitUntil(predicate, { timeoutMs = 8000, intervalMs = 100 } = {}) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(async () => {
      let value;
      try {
        value = await predicate();
      } catch (err) {
        clearInterval(timer);
        reject(err);
        return;
      }
      if (value) {
        clearInterval(timer);
        resolve(value);
        return;
      }
      if (Date.now() - startedAt > timeoutMs) {
        clearInterval(timer);
        reject(new Error(`waitUntil 超时（${timeoutMs}ms）`));
      }
    }, intervalMs);
  });
}

function request(port, pathname, { method = 'GET', token } = {}) {
  const headers = {};
  if (token !== undefined) headers['x-admin-token'] = token;
  return fetch(`http://127.0.0.1:${port}${pathname}`, { method, headers });
}

async function waitAgentAlive(agent, healthPort) {
  await waitUntil(async () => {
    if (agent.proc.exitCode !== null) throw new Error(`agent 提前退出 exit=${agent.proc.exitCode}`);
    try {
      const resp = await request(healthPort, '/healthz');
      return [200, 503].includes(resp.status);
    } catch {
      return false;
    }
  });
}

async function main() {
  const results = [];

  const runScenario = async (name, fn) => {
    const ctx = { agent: null, stub: null };
    try {
      await fn(ctx);
      results.push({ name, pass: true });
      console.log(`PASS ${name}`);
    } catch (err) {
      results.push({ name, pass: false, error: err.message });
      console.log(`FAIL ${name}: ${err.message}`);
      if (ctx.agent) console.log('  agent logs:', JSON.stringify(ctx.agent.logLines.slice(-6)));
    } finally {
      if (ctx.agent) await stopAgent(ctx.agent);
      if (ctx.stub) await ctx.stub.close().catch(() => {});
    }
  };

  await runScenario('healthz_admin_status_and_remote_config', async (ctx) => {
    ctx.stub = startStubPlatform();
    const stubPort = await ctx.stub.ready;
    const healthPort = randomHighPort();
    ctx.agent = spawnAgent({ stubPort, healthPort });
    await waitAgentAlive(ctx.agent, healthPort);

    const health = await request(healthPort, '/healthz');
    if (![200, 503].includes(health.status)) throw new Error(`healthz=${health.status}`);

    const noToken = await request(healthPort, '/admin/status');
    if (noToken.status !== 401) throw new Error(`无 token status=${noToken.status}`);

    const wrongToken = await request(healthPort, '/admin/status', { token: 'wrong-token' });
    if (wrongToken.status !== 401) throw new Error(`错 token status=${wrongToken.status}`);

    const ok = await request(healthPort, '/admin/status', { token: ADMIN_TOKEN });
    if (ok.status !== 200) throw new Error(`对 token status=${ok.status}`);
    const body = await ok.json();
    if (body.configVersion !== 1) throw new Error(`configVersion=${body.configVersion}（远程配置未合并）`);
    if (ctx.stub.configHits < 1) throw new Error('stub 未收到 agent.config 拉取');
  });

  await runScenario('admin_restart_exits_zero', async (ctx) => {
    ctx.stub = startStubPlatform();
    const stubPort = await ctx.stub.ready;
    const healthPort = randomHighPort();
    ctx.agent = spawnAgent({ stubPort, healthPort });
    await waitAgentAlive(ctx.agent, healthPort);

    const restart = await request(healthPort, '/admin/restart', { method: 'POST', token: ADMIN_TOKEN });
    if (restart.status !== 200) throw new Error(`restart=${restart.status}`);

    const exitCode = await Promise.race([
      new Promise((resolve) => ctx.agent.proc.on('exit', (code) => resolve(code))),
      new Promise((resolve) => setTimeout(() => resolve('timeout'), 2000)),
    ]);
    if (exitCode !== 0) throw new Error(`restart 后退出码=${exitCode}`);
  });

  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} scenarios passed`);
  process.exit(failed.length ? 1 : 0);
}

main().catch((err) => {
  console.error('ADMIN_API_TEST_ERROR', err);
  process.exit(1);
});
