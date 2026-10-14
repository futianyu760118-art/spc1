import http from 'node:http';
import { loadConfig } from './config.js';
import { createLogger } from './log.js';
import { createWsClient } from './ws-client.js';

function startHealthServer(port, client, log) {
  const server = http.createServer((req, res) => {
    if (req.url && req.url.split('?')[0] === '/healthz') {
      const ok = client.isRegistered();
      res.writeHead(ok ? 200 : 503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: ok ? 'ok' : 'not_registered' }));
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'not_found' }));
    }
  });
  server.on('error', (err) => log.error('health_server_error', { message: err.message }));
  server.listen(port, '127.0.0.1');
  log.info('health_server_listening', { port });
  return server;
}

function main() {
  const config = loadConfig();
  const log = createLogger(config.logLevel);
  if (!config.token) {
    log.error('missing_token', { env: 'EXECUTION_PLANE_TOKEN' });
    process.exit(1);
  }

  const client = createWsClient(config, log);
  let healthServer = null;
  if (config.healthCheckPort > 0) healthServer = startHealthServer(config.healthCheckPort, client, log);

  client.connect();

  const shutdown = (signal) => {
    log.info('exiting', { signal });
    client.stop();
    if (healthServer) healthServer.close();
    setTimeout(() => process.exit(0), 2000).unref();
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
  /* Windows 跨进程无法投递信号，以 IPC 通道作为等价优雅退出入口（仅以 ipc stdio 拉起时生效） */
  if (process.channel) {
    process.on('message', (message) => {
      if (message && message.type === 'shutdown') shutdown('ipc');
    });
  }
  process.on('uncaughtException', (err) => {
    log.error('uncaught_exception', { message: err.message, stack: err.stack });
    process.exit(1);
  });
  process.on('unhandledRejection', (reason) => {
    log.error('unhandled_rejection', { message: String(reason) });
    process.exit(1);
  });
}

main();
