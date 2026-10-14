FROM node:20-alpine

RUN apk add --no-cache python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages httpx python-dotenv

WORKDIR /app

COPY execution-agent/package.json execution-agent/package-lock.json ./
RUN npm ci --omit=dev

COPY execution-agent/src ./src
COPY execution-agent/query ./query

# 只读引用中台上游客户端（契约 §4.4 权威参考实现）
COPY mcp-company-control/mcp_server/upstream_client.py /app/vendor/upstream_client.py
ENV UPSTREAM_CLIENT_PATH=/app/vendor/upstream_client.py
ENV HEALTH_CHECK_PORT=8789

EXPOSE 8789
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD wget -q -O /dev/null http://127.0.0.1:8789/healthz || exit 1

ENTRYPOINT ["node", "src/agent.js"]
