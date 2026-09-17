ARG DSH_IMAGE=ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4

FROM ${DSH_IMAGE}

COPY plugin /tmp/ags-dsh-session-persistence

RUN npm install --global pnpm@11.19.0 \
    && cd /tmp/ags-dsh-session-persistence \
    && pnpm install --prod --frozen-lockfile \
    && mkdir -p /usr/local/lib/node_modules/@tencentcloud \
    && mv /tmp/ags-dsh-session-persistence \
      /usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence \
    && plugin_modules=/usr/local/lib/node_modules/@tencentcloud/ags-dsh-session-persistence/node_modules \
    && rm -rf "$plugin_modules/@deepseek-ai" \
    && mkdir -p "$plugin_modules/@deepseek-ai" \
    && for package in cordis dsh-session dsh-session-persistence dsh-tools schemastery; do \
         ln -s "/usr/local/lib/node_modules/@deepseek-ai/$package" "$plugin_modules/@deepseek-ai/$package"; \
       done \
    && rm -rf /root/.npm /root/.local/share/pnpm/store

COPY dockerfiles/agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
COPY dockerfiles/settings.yaml /root/.dsh/settings.yaml
COPY dockerfiles/entrypoint.sh /opt/dsh/entrypoint.sh

RUN chmod 0755 /opt/dsh/entrypoint.sh

ENTRYPOINT ["/opt/dsh/entrypoint.sh"]
CMD []
