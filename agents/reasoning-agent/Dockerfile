FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
COPY runtime/package.json ./runtime/package.json
COPY query-agent/package.json ./query-agent/package.json
COPY reasoning-agent/package.json ./reasoning-agent/package.json
RUN npm ci --omit=dev

COPY runtime ./runtime
COPY reasoning-agent ./reasoning-agent

WORKDIR /app/reasoning-agent
EXPOSE 8790
ENV NODE_ENV=production
USER node
CMD ["node", "src/index.js"]
