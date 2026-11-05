ARG NODE_IMAGE=docker.io/library/node:24.8.0-bookworm-slim

FROM ${NODE_IMAGE}

# The version is pinned: the extension was written against this release's
# extension events and session file format.
ARG PI_VERSION=1.4.0
RUN npm install --global --no-audit --no-fund @earendil-works/pi-coding-agent@${PI_VERSION} \
    && rm -rf /root/.npm

COPY extension/package.json extension/package-lock.json /opt/pi/extension/
RUN cd /opt/pi/extension && npm ci --omit=dev --no-audit --no-fund && rm -rf /root/.npm
COPY extension/*.js extension/*.mjs /opt/pi/extension/
RUN rm -f /opt/pi/extension/*.test.js

# The minimal in-memory example imports pi as a library, so it resolves the scope from /opt/pi/node_modules.
COPY minimal/ /opt/pi/minimal/
RUN mkdir -p /opt/pi/node_modules \
    && ln -s /usr/local/lib/node_modules/@earendil-works /opt/pi/node_modules/@earendil-works

COPY dockerfiles/entrypoint.sh /opt/pi/entrypoint.sh
RUN chmod 0755 /opt/pi/entrypoint.sh && mkdir -p /workspace /var/pi/sessions

WORKDIR /workspace
ENV PI_OFFLINE=1 PI_TELEMETRY=0 PI_SKIP_VERSION_CHECK=1
ENTRYPOINT ["/opt/pi/entrypoint.sh"]
