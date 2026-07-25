FROM ccr.ccs.tencentyun.com/ags-image/envd:v0.5.14 AS envd-provider

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl git procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=envd-provider /usr/bin/envd /usr/bin/envd
COPY images/main/demo_server.py /opt/claude-demo/demo_server.py
COPY images/main/start_demo.py /usr/local/bin/start-demo

RUN chmod 0755 /usr/bin/envd /usr/local/bin/start-demo

WORKDIR /workspace
ENV DEMO_STATE_DIR=/workspace/demo-result \
    DEMO_HTTP_PORT=8080 \
    ENVD_PORT=49983

EXPOSE 49983 8080
CMD ["/usr/local/bin/start-demo"]
