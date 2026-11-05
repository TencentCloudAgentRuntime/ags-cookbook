# Stateless handoff reference image.
#
# Unlike the base 0.2.1-rc.2 example, this image cannot install the published
# @deepseek-ai/dsh release: the handoff hook lives in a source patch to
# session-controller. Build DSH from the pinned tag, then install the packed
# workspace the same way the deployment cookbook's all-in-one image does.
#
# Build context: this directory (the reference root).

ARG NODE_IMAGE=docker.io/library/node:24.8.0-bookworm-slim
ARG DEEPSEEK_HARNESS_TAG=dsh-v0.2.1-rc.2
ARG DEEPSEEK_HARNESS_COMMIT=687f282e8625c6b8d11ff58211a90524be2e4317

FROM --platform=${BUILDPLATFORM} ${NODE_IMAGE} AS build

ARG DEEPSEEK_HARNESS_TAG
ARG DEEPSEEK_HARNESS_COMMIT

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git g++ make python3 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install --global pnpm@11.28.5

WORKDIR /opt

RUN git clone --depth 1 --branch "$DEEPSEEK_HARNESS_TAG" \
      https://github.com/deepseek-ai/deepseek-harness.git \
      /opt/deepseek-harness \
    && git -C /opt/deepseek-harness rev-parse HEAD \
       | grep --fixed-strings --line-regexp "$DEEPSEEK_HARNESS_COMMIT"

COPY dockerfiles/0001-stateless-handoff.patch /tmp/0001-stateless-handoff.patch

WORKDIR /opt/deepseek-harness

RUN git apply --check /tmp/0001-stateless-handoff.patch \
    && git apply /tmp/0001-stateless-handoff.patch

RUN pnpm install --frozen-lockfile

# Guard the two behaviours the patch changes: Agent handle ownership and the
# prompt admission path.
RUN pnpm exec vitest run \
      packages/api/session-controller/tests/agent.host.spec.ts \
      packages/api/session-controller/tests/commands-queue-attachment.host.spec.ts \
      packages/api/session-controller/tests/controller.host.spec.ts

RUN pnpm run build:official

RUN pnpm release:pack --family vendor --out dist/npm-vendor \
    && pnpm release:pack --family dsh --out dist/npm-dsh

FROM ${NODE_IMAGE}

COPY --from=build /opt/deepseek-harness/dist/npm-vendor /tmp/vendor-tarballs
COPY --from=build /opt/deepseek-harness/dist/npm-dsh /tmp/dsh-tarballs

RUN npm install --global --no-audit --no-fund --omit=optional \
      /tmp/vendor-tarballs/*.tgz \
      /tmp/dsh-tarballs/*.tgz \
    && rm -rf /tmp/vendor-tarballs /tmp/dsh-tarballs /root/.npm

ENV DSH_HOME=/root/.dsh

# Where DSH's own @deepseek-ai packages are installed. npm 11 nests them under
# the dsh package. If a future release hoists them, override this build arg.
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

COPY plugin /tmp/ags-dsh-session-persistence

# Install the plugin, then link the DSH packages it shares with DSH to DSH's own
# copy, so both use one cordis, Session, and persistence module instance.
RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p "$(dirname "$PLUGIN_DIR")" \
    && rm -rf "$PLUGIN_DIR" \
    && mv /tmp/ags-dsh-session-persistence "$PLUGIN_DIR" \
    && rm -rf "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && mkdir -p "$PLUGIN_DIR/node_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence schemastery; do \
         ln -s "$DSH_MODULES/$package" "$PLUGIN_DIR/node_modules/@deepseek-ai/$package"; \
       done \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

COPY dockerfiles/agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
COPY dockerfiles/entrypoint.sh /opt/dsh/entrypoint.sh

RUN chmod 0755 /opt/dsh/entrypoint.sh

WORKDIR /workspace

EXPOSE 3080

ENTRYPOINT ["/opt/dsh/entrypoint.sh"]
CMD []
