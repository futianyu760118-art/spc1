import { WebSocketServer } from 'ws';

export function waitUntil(predicate, { timeoutMs = 8000, intervalMs = 25 } = {}) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();
    const timer = setInterval(() => {
      let value;
      try {
        value = predicate();
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

export function startMockHub({ port = 0, token = 'test-token', heartbeatIntervalMs = 150 } = {}) {
  const wss = new WebSocketServer({ port });
  const state = { wss, port, received: [], sockets: new Set() };
  const ready = new Promise((resolve) =>
    wss.on('listening', () => {
      state.port = wss.address().port;
      resolve();
    })
  );

  wss.on('connection', (ws, req) => {
    if (req.headers['x-aeos-execution-token'] !== token) {
      ws.close(4001, 'unauthorized');
      return;
    }
    state.sockets.add(ws);
    ws.on('message', (raw) => {
      const message = JSON.parse(raw.toString());
      state.received.push(message);
      if (message.type === 'register') {
        ws.send(JSON.stringify({ type: 'registered', agentId: message.agentId, heartbeatIntervalMs }));
      }
    });
    ws.on('close', () => state.sockets.delete(ws));
  });

  return {
    ready,
    get port() {
      return state.port;
    },
    get received() {
      return state.received;
    },
    send(message) {
      const raw = JSON.stringify(message);
      for (const ws of state.sockets) {
        if (ws.readyState === ws.OPEN) ws.send(raw);
      }
    },
    async close() {
      for (const ws of state.sockets) ws.terminate();
      await new Promise((resolve) => wss.close(() => resolve()));
    },
  };
}
