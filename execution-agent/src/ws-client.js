import WebSocket from 'ws';
import { CAPABILITY_NAME } from './config.js';
import { createRunner } from './runner.js';

/** 重连退避阶梯（秒级递增至 30s 封顶），每次叠加 ±20% 随机抖动（交接单要求 1/2/5/10/30） */
const RECONNECT_LADDER_MS = [1000, 2000, 5000, 10000, 30000];
const DEFAULT_HEARTBEAT_MS = 5000;

/** WS 状态机：register → registered → 心跳；断线杀 run、指数退避重连后重新 register（契约 §5） */
export function createWsClient(config, log) {
  const runner = createRunner(config, log);
  let ws = null;
  let heartbeatTimer = null;
  let heartbeatIntervalMs = DEFAULT_HEARTBEAT_MS;
  let registered = false;
  let reconnectStep = 0;
  let reconnectTimer = null;
  let stopped = false;

  function send(message) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(message));
  }

  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      const message = { type: 'heartbeat', status: runner.isBusy() ? 'working' : 'idle' };
      const currentRunId = runner.currentRunId();
      if (currentRunId) message.currentRunId = currentRunId;
      send(message);
      log.debug('heartbeat_sent', { status: message.status });
    }, heartbeatIntervalMs);
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function handleMessage(message) {
    switch (message.type) {
      case 'registered': {
        const interval = Number(message.heartbeatIntervalMs);
        heartbeatIntervalMs = Number.isFinite(interval) && interval > 0 ? interval : DEFAULT_HEARTBEAT_MS;
        registered = true;
        reconnectStep = 0;
        startHeartbeat();
        log.info('registered', { agentId: message.agentId, heartbeatIntervalMs });
        break;
      }
      case 'dispatch': {
        log.info('dispatch_received', { runId: message.runId, capability: message.capability });
        try {
          runner.start(message, send);
        } catch (err) {
          send({
            type: 'run_failed',
            runId: message.runId,
            error: { code: 'INTERNAL_ERROR', message: `dispatch 处理异常: ${err.message}` },
          });
        }
        break;
      }
      case 'recall':
        runner.recall(message.runId);
        break;
      case 'error':
        log.warn('protocol_error', { message: message.message });
        break;
      default:
        log.warn('unknown_message_type', { type: message.type });
    }
  }

  function scheduleReconnect() {
    const base = RECONNECT_LADDER_MS[Math.min(reconnectStep, RECONNECT_LADDER_MS.length - 1)];
    reconnectStep = Math.min(reconnectStep + 1, RECONNECT_LADDER_MS.length - 1);
    const delay = Math.round(base * (0.8 + Math.random() * 0.4));
    log.info('reconnecting', { delayMs: delay });
    reconnectTimer = setTimeout(connect, delay);
  }

  function connect() {
    if (stopped) return;
    ws = new WebSocket(config.wsUrl, { headers: { 'x-aeos-execution-token': config.token } });
    ws.on('open', () => {
      log.info('connected', { wsUrl: config.wsUrl });
      send({
        type: 'register',
        agentId: config.agentId,
        name: config.agentName,
        version: config.agentVersion,
        ...(config.sourceSystem ? { sourceSystem: config.sourceSystem } : {}),
        capabilities: [{ name: CAPABILITY_NAME, description: '中台只读查询' }],
      });
    });
    ws.on('message', (raw) => {
      let message;
      try {
        message = JSON.parse(raw.toString());
      } catch {
        log.warn('invalid_json_frame', {});
        return;
      }
      if (message && typeof message === 'object') handleMessage(message);
    });
    ws.on('error', (err) => log.warn('ws_error', { message: err.message }));
    ws.on('close', () => {
      const wasRegistered = registered;
      registered = false;
      stopHeartbeat();
      runner.abortActive();
      if (stopped) return;
      log.info('disconnected', { wasRegistered });
      scheduleReconnect();
    });
  }

  function stop() {
    stopped = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    stopHeartbeat();
    runner.abortActive();
    if (ws) {
      try {
        ws.close(1000, 'agent shutdown');
      } catch {
        /* 已关闭 */
      }
    }
  }

  return { connect, stop, isRegistered: () => registered };
}
