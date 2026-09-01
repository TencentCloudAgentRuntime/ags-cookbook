ARG NODE_IMAGE=docker.io/library/node:22.23.2-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32
FROM ${NODE_IMAGE}

LABEL org.opencontainers.image.title="Everything MCP Server for AGR Deployment examples" \
      org.opencontainers.image.source="https://github.com/modelcontextprotocol/servers" \
      org.opencontainers.image.version="2026.8.31-ags.1" \
      org.opencontainers.image.revision="a40bc270fb5ece62673f8a1196f57116d885c5eb" \
      org.opencontainers.image.licenses="Apache-2.0 AND MIT"

ENV NODE_ENV=production \
    PORT=3001 \
    HEALTH_PORT=3000

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm --registry=https://mirrors.cloud.tencent.com/npm/ \
      ci --omit=dev --ignore-scripts --no-audit --no-fund \
    && npm cache clean --force

COPY entrypoint.mjs LICENSE-modelcontextprotocol-servers ./

USER node
EXPOSE 3000 3001

ENTRYPOINT ["node", "entrypoint.mjs"]
