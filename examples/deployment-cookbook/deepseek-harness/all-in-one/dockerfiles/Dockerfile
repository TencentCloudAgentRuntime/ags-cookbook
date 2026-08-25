ARG NODE_IMAGE=docker.io/library/node:24.8.0-bookworm-slim

FROM --platform=${BUILDPLATFORM} ${NODE_IMAGE} AS build

ARG DEEPSEEK_HARNESS_TAG=dsh-v0.1.1-rc.2
ARG DEEPSEEK_HARNESS_COMMIT=b150a551b8d465e31e418e1b2eaf5e79bbb7d28e

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git g++ make python3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global pnpm@11.7.0

WORKDIR /opt

RUN git clone --depth 1 --branch "$DEEPSEEK_HARNESS_TAG" \
      https://github.com/deepseek-ai/deepseek-harness.git \
      /opt/deepseek-harness \
    && git -C /opt/deepseek-harness rev-parse HEAD | grep --fixed-strings --line-regexp "$DEEPSEEK_HARNESS_COMMIT"

COPY 0001-support-ags-deployment-web.patch /tmp/0001-support-ags-deployment-web.patch

WORKDIR /opt/deepseek-harness

RUN git apply --unidiff-zero --check /tmp/0001-support-ags-deployment-web.patch \
    && git apply --unidiff-zero /tmp/0001-support-ags-deployment-web.patch

RUN pnpm install --frozen-lockfile

RUN pnpm exec vitest run \
      packages/bundle/web-app/tests/startup.spec.ts \
      packages/client/connection/tests/api-request-trust.host.spec.ts

RUN pnpm run build:official

RUN pnpm release:pack --family vendor --out dist/npm-vendor \
    && pnpm release:pack --family dsh --out dist/npm-dsh

FROM --platform=linux/amd64 ${NODE_IMAGE}

COPY --from=build /opt/deepseek-harness/dist/npm-vendor /tmp/vendor-tarballs
COPY --from=build /opt/deepseek-harness/dist/npm-dsh /tmp/dsh-tarballs

RUN npm install --global --no-audit --no-fund --omit=optional \
      /tmp/vendor-tarballs/*.tgz \
      /tmp/dsh-tarballs/*.tgz \
    && rm -rf /tmp/vendor-tarballs /tmp/dsh-tarballs /root/.npm

ENV DSH_HOME=/root/.dsh

WORKDIR /workspace

EXPOSE 3080

ENTRYPOINT ["node", "--expose-internals", "/usr/local/lib/node_modules/@deepseek-ai/dsh/lib/bin.js"]
CMD ["web", "--host", "0.0.0.0", "--port", "3080", "--trusted-host", "*.ap-shanghai.agents.tencentags.com", "--trusted-host", "*.ap-shanghai.internal.tencentags.com", "--no-open"]
