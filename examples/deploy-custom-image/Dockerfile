ARG SOURCE_IMAGE

FROM ${SOURCE_IMAGE}
USER root
COPY --from=ccr.ccs.tencentyun.com/ags-image/envd:latest /usr/bin/envd /usr/bin/envd
RUN chmod +x /usr/bin/envd
