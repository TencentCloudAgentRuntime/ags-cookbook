FROM ccr.ccs.tencentyun.com/ags-image/envd:v0.5.14 AS envd-provider

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl git procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=envd-provider /usr/bin/envd /usr/bin/envd

RUN chmod 0755 /usr/bin/envd \
    && mkdir -p /workspace/report

WORKDIR /workspace
ENV DEMO_REPORT_DIR=/workspace/report \
    DEMO_HTTP_PORT=8080 \
    ENVD_PORT=49983

EXPOSE 49983 8080
CMD ["/bin/sh", "-c", "/usr/bin/envd -port \"$ENVD_PORT\" & exec python3 -m http.server \"$DEMO_HTTP_PORT\" --bind 0.0.0.0 --directory \"$DEMO_REPORT_DIR\""]
