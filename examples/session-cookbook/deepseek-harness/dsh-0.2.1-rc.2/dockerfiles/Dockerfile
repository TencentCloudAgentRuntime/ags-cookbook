ARG NODE_IMAGE=docker.io/library/node:24.8.0-bookworm-slim
# Build on your own DSH image instead: --build-arg DSH_IMAGE=your-registry/your-dsh:version
ARG DSH_IMAGE=official-dsh

# The official DeepSeek Harness release from npm, without patches. The version is
# pinned: plugin/package.json peerDependencies match exactly this release.
FROM ${NODE_IMAGE} AS official-dsh
RUN npm install --global --no-audit --no-fund --omit=optional @deepseek-ai/dsh@0.2.1-rc.2 \
    && rm -rf /root/.npm
ENV DSH_HOME=/root/.dsh

FROM ${DSH_IMAGE}

# Where DSH's own @deepseek-ai packages are installed. npm 11 nests them under the dsh package.
ARG DSH_MODULES=/usr/local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai
ARG PLUGIN_DIR=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence

COPY plugin /tmp/ags-dsh-session-persistence

# Install the plugin, then link the DSH packages it shares with DSH to DSH's own copy,
# so both use one cordis, Session, and persistence module instance.
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
