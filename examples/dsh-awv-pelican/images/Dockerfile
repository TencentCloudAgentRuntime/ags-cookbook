# syntax=docker/dockerfile:1.7
FROM node:22.19.0-bookworm-slim@sha256:cff78eb5aa1cf27dc2b6aeea9d31366415a43e9a9ea0ddec00d780b2b66fad0f AS base

ARG KUBECTL_VERSION=v1.36.2
ENV pnpm_config_store_dir=/opt/pnpm/store
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tini \
 && rm -rf /var/lib/apt/lists/* \
 && npm install --global "pnpm@11.19.0"
COPY images/harness/package.json images/harness/pnpm-lock.yaml images/harness/pnpm-workspace.yaml /opt/harness/
RUN cd /opt/harness && pnpm install --frozen-lockfile --ignore-scripts
ENV PATH="/opt/harness/node_modules/.bin:${PATH}"

FROM base AS plugin-builder
WORKDIR /build/plugin
COPY plugin/dsh-agc/package.json plugin/dsh-agc/pnpm-lock.yaml plugin/dsh-agc/pnpm-workspace.yaml plugin/dsh-agc/tsconfig.json ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY plugin/dsh-agc/src ./src
COPY plugin/dsh-agc/cordis.patch.yml ./
RUN pnpm run build && pnpm pack --pack-destination /tmp

FROM base AS controller
ENV DSH_HOME=/opt/dsh
RUN curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
 && chmod 0755 /usr/local/bin/kubectl
COPY --from=plugin-builder /tmp/agc-dsh-k8s-0.1.0.tgz /tmp/dsh-agc.tgz
COPY images/controller/web.patch.yml /opt/pelican/controller/web.patch.yml
RUN dsh --profile agc-web --from-default-profile web --dump-config >/dev/null \
 && dsh plugin --profile agc-web add /tmp/dsh-agc.tgz \
 && dsh --profile agc-headless --from-default-profile headless --dump-config >/dev/null \
 && dsh plugin --profile agc-headless add /tmp/dsh-agc.tgz \
 && node --input-type=module -e 'import fs from "node:fs"; for (const name of ["agc-web", "agc-headless"]) { const file = `/opt/dsh/profiles/${name}/package.json`; const manifest = JSON.parse(fs.readFileSync(file, "utf8")); manifest.dsh.profile.patchReload = "startup"; fs.writeFileSync(file, JSON.stringify(manifest, null, 2)); }' \
 && chown -R 10001:10001 /opt/dsh \
 && rm /tmp/dsh-agc.tgz
USER 10001:10001
EXPOSE 3080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["dsh", "--profile", "agc-web", "--patch", "/opt/pelican/controller/web.patch.yml", "--no-open"]

FROM base AS worker
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
COPY images/worker/package.json images/worker/pnpm-lock.yaml /opt/pelican/browser/
RUN cd /opt/pelican/browser \
 && pnpm install --frozen-lockfile --ignore-scripts \
 && ./node_modules/.bin/playwright install --with-deps chrome \
 && rm -rf /var/lib/apt/lists/*
ENV HOME=/tmp/dsh
COPY images/worker/profiles /opt/pelican/profiles
RUN mkdir -p /workspace/site /tmp/dsh /tmp/review \
 && chown -R 10001:10001 /workspace /tmp/dsh /tmp/review
USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["dsh", "--profile", "headless", "--help"]
