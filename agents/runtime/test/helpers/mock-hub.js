"use strict";

const http = require("node:http");
const WebSocket = require("ws");
const { WebSocketServer } = require("ws");

function startHub({ heartbeatIntervalMs = 10000 } = {}) {
  const messages = [];
  const tokens = [];
  const server = http.createServer();
  const wss = new WebSocketServer({ server, path: "/execution-agent" });
  let connectionCount = 0;

  const ready = new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve(server.address().port));
  });

  wss.on("connection", (socket, req) => {
    connectionCount += 1;
    tokens.push(req.headers["x-aeos-execution-token"]);
    socket.on("message", (raw) => {
      const message = JSON.parse(raw.toString());
      messages.push(message);
      if (message.type === "register") {
        socket.send(JSON.stringify({ type: "registered", agentId: message.agentId, heartbeatIntervalMs }));
      }
    });
  });

  function currentSocket() {
    return [...wss.clients].reverse().find((socket) => socket.readyState === WebSocket.OPEN);
  }

  return {
    ready,
    messages,
    tokens,
    get connectionCount() {
      return connectionCount;
    },
    send(payload) {
      const socket = currentSocket();
      if (socket) socket.send(JSON.stringify(payload));
    },
    disconnectClient() {
      const socket = currentSocket();
      if (socket) socket.close(1001, "test disconnect");
    },
    async close() {
      for (const socket of wss.clients) socket.terminate();
      await new Promise((resolve) => wss.close(resolve));
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

module.exports = { startHub };
