ARG NODE_IMAGE=docker.io/library/node:24.8.0-bookworm-slim

FROM --platform=linux/amd64 ${NODE_IMAGE} AS build

ARG NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/

RUN npm config set registry "${NPM_REGISTRY}" \
    && npm install --global pnpm@11.19.0 \
    && pnpm config set registry "${NPM_REGISTRY}"

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY patches ./patches
COPY plugins ./plugins

RUN pnpm install --frozen-lockfile

COPY tsconfig.json tsconfig.build.json ./
COPY src ./src
COPY migrations ./migrations
COPY web ./web

RUN pnpm build \
    && pnpm install --prod --offline --frozen-lockfile

FROM --platform=linux/amd64 ${NODE_IMAGE}

ENV NODE_ENV=production

WORKDIR /app

COPY --from=build --chown=node:node /app/package.json ./package.json
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/dist ./dist
COPY --from=build --chown=node:node /app/migrations ./migrations
COPY --from=build --chown=node:node /app/web ./web

RUN mkdir -p /workspace \
    && chown node:node /workspace

USER node

EXPOSE 8080/tcp 3080/tcp
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:8080/readyz').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]

ENTRYPOINT ["node", "/app/dist/brain/launcher.js"]
