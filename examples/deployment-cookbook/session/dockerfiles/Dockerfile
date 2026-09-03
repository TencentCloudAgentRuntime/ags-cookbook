ARG DSH_IMAGE=ccr.ccs.tencentyun.com/ags.dev/deepseek-harness:v0.1.1-rc.2-ags.4

FROM ${DSH_IMAGE}

COPY plugin /tmp/ags-dsh-session-persistence

RUN cd /tmp/ags-dsh-session-persistence \
    && npm pack --pack-destination /tmp \
    && npm install --global --no-audit --no-fund /tmp/tencentcloud-ags-dsh-session-persistence-0.1.0.tgz \
    && rm -rf /tmp/ags-dsh-session-persistence \
      /tmp/tencentcloud-ags-dsh-session-persistence-0.1.0.tgz \
      /root/.npm

COPY dockerfiles/agent-runtime-session.cordis.yml /opt/dsh/agent-runtime-session.cordis.yml
COPY dockerfiles/settings.yaml /root/.dsh/settings.yaml
COPY dockerfiles/entrypoint.sh /opt/dsh/entrypoint.sh

RUN chmod 0755 /opt/dsh/entrypoint.sh

ENTRYPOINT ["/opt/dsh/entrypoint.sh"]
CMD []
