import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const AGENT_DIR = path.resolve(__dirname, '..');
export const REPO_ROOT = path.resolve(AGENT_DIR, '..');

export const CAPABILITY_NAME = 'query_control_platform';

/** 契约 §4.2 白名单（冻结值）；与 upstream_client._ENDPOINT_CODES 双份维护，新增端点两处同步 */
export const PATH_WHITELIST = Object.freeze([
  '/common/ping',
  '/external/orders/list',
  '/external/order-details/list',
  '/external/boms/tree',
  '/external/materials/list',
  '/external/suppliers/list',
  '/external/material-kitting/results',
  '/external/material-kitting/shortages',
  '/external/material-kitting/demands',
  '/external/inventory/availability',
  '/external/material-supplies/list',
  '/external/quality-issues/list',
  '/external/quality-trace/list',
  '/external/production/work-orders/list',
  '/external/production/operations/list',
  '/external/production/order-links/list',
  '/external/production/reports/list',
  '/external/production/capacity/list',
]);

function readAgentVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(AGENT_DIR, 'package.json'), 'utf8')).version;
  } catch {
    return '0.0.0';
  }
}

function toInt(value, fallback) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function loadConfig(env = process.env) {
  return {
    wsUrl: env.EXECUTION_WS_URL || 'ws://127.0.0.1:8788/execution-agent',
    token: env.EXECUTION_PLANE_TOKEN || '',
    agentId: env.EXECUTION_AGENT_ID || 'runtime-execution-query',
    agentName: env.AGENT_NAME || 'execution-query-agent',
    sourceSystem: env.EXECUTION_SOURCE_SYSTEM || '',
    agentVersion: env.AGENT_VERSION || readAgentVersion(),
    pythonBin: env.PYTHON_BIN || 'python',
    queryScript: env.QUERY_SCRIPT || path.join(AGENT_DIR, 'query', 'company-control-query.py'),
    upstreamClientPath:
      env.UPSTREAM_CLIENT_PATH ||
      path.join(REPO_ROOT, 'mcp-company-control', 'mcp_server', 'upstream_client.py'),
    queryTimeoutMs: toInt(env.QUERY_TIMEOUT_MS, 30000),
    healthCheckPort: toInt(env.HEALTH_CHECK_PORT, 8789),
    logLevel: env.LOG_LEVEL || 'info',
  };
}
