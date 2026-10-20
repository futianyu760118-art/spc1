FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
COPY runtime/package.json ./runtime/package.json
COPY query-agent/package.json ./query-agent/package.json
COPY reasoning-agent/package.json ./reasoning-agent/package.json
COPY order-agent/package.json ./order-agent/package.json
RUN npm ci --omit=dev

COPY runtime ./runtime
COPY order-agent ./order-agent

WORKDIR /app/order-agent
ENV NODE_ENV=production
USER node
EXPOSE 8790
CMD ["node", "src/index.js"]
