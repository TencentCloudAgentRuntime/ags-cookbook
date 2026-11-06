# Stateless handoff reference image.
#
# Unlike the base 0.2.1-rc.2 example, this image cannot install the published
# @deepseek-ai/dsh release: the handoff hook lives in a source patch to
# session-controller and the turn admission barrier. Build the pinned source
# and preserve its compiled workspace dependency graph.
#
# Build context: this directory (the reference root).

ARG BUILD_IMAGE=node:24.22.2-bookworm-slim
ARG RUNTIME_IMAGE=node:24.8.0-bookworm-slim
ARG DEEPSEEK_HARNESS_TAG=dsh-v0.2.1-rc.2
ARG DEEPSEEK_HARNESS_COMMIT=687f282e8625c6b8d11ff58211a90524be2e4317

# The build stage needs apt (git, g++, make, python3). The 24.8.0 bookworm image
# predates the Debian archive key rotation, so its keyring cannot verify the
# current bookworm repository. The build image is therefore newer than the
# runtime image; override BUILD_IMAGE if your registry mirrors a different one.
FROM ${BUILD_IMAGE} AS build

ARG DEEPSEEK_HARNESS_TAG
ARG DEEPSEEK_HARNESS_COMMIT
# Optional cap on DSH build-gate parallelism. DSH defaults to the CPU count;
# lower it (for example 1 or 2) on memory-constrained builders, because
# `build:official` runs the host compiler, bundle, and aggregate check in
# parallel and can OOM a small Docker VM.
ARG DSH_GATE_CONCURRENCY

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

# One lockfile entry (xlsx) is fetched from cdn.sheetjs.com and can take many
# minutes on a slow network. Keep the pnpm store in a BuildKit cache so a
# retried build reuses everything already downloaded, and allow a long fetch.
RUN --mount=type=cache,target=/pnpm/store \
    pnpm install --frozen-lockfile --store-dir=/pnpm/store --fetch-timeout=1800000

# Fast guard before the long build: the session-controller changes (Agent handle
# ownership, prompt admission) need no native addon.
RUN pnpm exec vitest run \
      packages/api/session-controller/tests/agent.host.spec.ts \
      packages/api/session-controller/tests/commands-queue-attachment.host.spec.ts \
      packages/api/session-controller/tests/controller.host.spec.ts

RUN if [ -n "$DSH_GATE_CONCURRENCY" ]; then \
      DSH_GATE_CONCURRENCY="$DSH_GATE_CONCURRENCY" pnpm run build:official; \
    else \
      pnpm run build:official; \
    fi

# The agent-loop suite protects the turn-claim barrier and the synchronous
# turn/start append that steer() relies on. Part of it takes file locks through
# the native system addon, which `build:official` compiles, so it must run after
# the build rather than before it.
RUN pnpm exec vitest run packages/core/agent-loop/tests

FROM ${RUNTIME_IMAGE}

# Preserve the already-built workspace dependency graph. Installing every packed
# package globally re-resolves hundreds of packages and can exhaust builder RAM.
# This runtime deliberately keeps the workspace layout used by the verified build.
COPY --from=build /opt/deepseek-harness /opt/deepseek-harness
RUN ln -s /opt/deepseek-harness/apps/cli/lib/bin.js /usr/local/bin/dsh

ENV DSH_HOME=/root/.dsh

# Packages shared with the compiled DSH workspace.
ARG DSH_MODULES=/opt/deepseek-harness/apps/cli/node_modules/@deepseek-ai
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
    && ln -sfn /opt/deepseek-harness/packages/session/session-persistence "$PLUGIN_DIR/node_modules/@deepseek-ai/dsh-session-persistence" \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

COPY dockerfiles/agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
COPY dockerfiles/entrypoint.sh /opt/dsh/entrypoint.sh

RUN chmod 0755 /opt/dsh/entrypoint.sh

WORKDIR /workspace

EXPOSE 3080

ENTRYPOINT ["/opt/dsh/entrypoint.sh"]
CMD []
