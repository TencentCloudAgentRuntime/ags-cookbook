ARG GO_IMAGE=golang:1.25.9-bookworm
ARG BASE_IMAGE=docker:29.3.1-dind@sha256:686d2c5464787b0ca42420e0aa03a94fc9781ff9bf8b5ff947614b9fa4c3c3e0

FROM ${GO_IMAGE} AS envd-builder

ARG ENVD_BUILD_REVISION=unknown
WORKDIR /workspace
COPY utils/envd/versions/0.5.14-oci/src ./src
COPY utils/envd/versions/0.5.14-oci/shared ./shared
WORKDIR /workspace/src
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build \
      -trimpath \
      -buildvcs=false \
      -a \
      -o /out/envd \
      -ldflags "-X=main.commitSHA=${ENVD_BUILD_REVISION} -s -w -buildid=" \
      .

FROM ${BASE_IMAGE}

USER root

# Build the OCI-aware envd distribution from its vendored, auditable source.
COPY --from=envd-builder --chmod=755 /out/envd /usr/bin/envd
COPY --chmod=755 examples/dind/image/entrypoint.sh /usr/local/bin/ags-dind-entrypoint

RUN apk add --no-cache bash util-linux \
    && adduser -D -u 1000 -G docker user \
    && mkdir -p /workspace \
    && chown user:docker /workspace

ENV DOCKER_HOST=unix:///var/run/docker.sock \
    DOCKER_TLS_CERTDIR="" \
    ENVD_DISTRIBUTION=0.5.14-oci \
    TINI_SUBREAPER=1 \
    DIND_BLOCK_DEVICE=/dev/vda \
    DIND_MOUNT_POINT=/mnt \
    DIND_STATE_DIR=/mnt/dind \
    DIND_REQUIRE_EXTERNAL_STORAGE=1 \
    DIND_READY_TIMEOUT_SECONDS=180 \
    ENVD_PORT=49983

EXPOSE 49983
WORKDIR /workspace

HEALTHCHECK --interval=10s --timeout=3s --start-period=180s --retries=3 \
    CMD docker info >/dev/null 2>&1 && wget -q -O /dev/null "http://127.0.0.1:${ENVD_PORT}/health"

STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/local/bin/ags-dind-entrypoint"]
CMD []
