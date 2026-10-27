FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
COPY runtime/package.json ./runtime/package.json
COPY query-agent/package.json ./query-agent/package.json
COPY reasoning-agent/package.json ./reasoning-agent/package.json
COPY order-agent/package.json ./order-agent/package.json
COPY gateway-agent/package.json ./gateway-agent/package.json
RUN npm ci --omit=dev

COPY runtime ./runtime
COPY query-agent ./query-agent
COPY reasoning-agent ./reasoning-agent
COPY gateway-agent ./gateway-agent

WORKDIR /app/gateway-agent
ENV NODE_ENV=production
ENV NODE_EXTRA_CA_CERTS=/app/certs/caddy-root.crt
EXPOSE 8790
USER node
CMD ["node", "src/index.js"]
