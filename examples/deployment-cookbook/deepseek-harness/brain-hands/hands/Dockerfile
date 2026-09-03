ARG ENVD_BUILDER_IMAGE=docker.io/library/golang:1.26.5-alpine
ARG UBUNTU_RUNTIME_IMAGE=docker.io/library/ubuntu:24.04
ARG ALPINE_RUNTIME_IMAGE=docker.io/library/alpine:3.22
ARG HANDS_OS=ubuntu

FROM ${ENVD_BUILDER_IMAGE} AS envd-builder

ARG ENVD_COMMIT=2acf2d51bd1e2fe146914f24c44f7ee07d2213c5
ARG ENVD_VERSION=0.6.13
ENV GOPROXY=https://mirrors.cloud.tencent.com/go/,direct \
    GOSUMDB=sum.golang.org

RUN set -eux; \
    sed -i 's|https\?://dl-cdn.alpinelinux.org/alpine|https://mirrors.cloud.tencent.com/alpine|g' /etc/apk/repositories; \
    apk add --no-cache ca-certificates git; \
    install -d /out; \
    git init /src; \
    git -C /src remote add origin https://github.com/e2b-dev/infra.git; \
    git -C /src fetch --depth 1 origin "${ENVD_COMMIT}"; \
    git -C /src checkout --detach FETCH_HEAD; \
    test "$(git -C /src rev-parse HEAD)" = "${ENVD_COMMIT}"; \
    cd /src/packages/envd; \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -buildvcs=false -a \
      -ldflags "-X=main.commitSHA=$(printf '%.7s' "${ENVD_COMMIT}") -s -w -buildid=" \
      -o /out/envd; \
    test "$(/out/envd -version)" = "${ENVD_VERSION}"; \
    cp /src/LICENSE /out/LICENSE

FROM ${UBUNTU_RUNTIME_IMAGE} AS ubuntu-runtime

RUN set -eux; \
    for file in /etc/apt/sources.list /etc/apt/sources.list.d/ubuntu.sources; do \
      [ -f "${file}" ] || continue; \
      sed -i \
        -e 's|https\?://archive.ubuntu.com/ubuntu|http://mirrors.cloud.tencent.com/ubuntu|g' \
        -e 's|https\?://security.ubuntu.com/ubuntu|http://mirrors.cloud.tencent.com/ubuntu|g' \
        -e 's|https\?://ports.ubuntu.com/ubuntu-ports|http://mirrors.cloud.tencent.com/ubuntu-ports|g' \
        "${file}"; \
    done; \
    apt-get update; \
    apt-get install -y --no-install-recommends bash ca-certificates curl git procps ripgrep util-linux; \
    rm -rf /var/lib/apt/lists/*

FROM ${ALPINE_RUNTIME_IMAGE} AS alpine-runtime

RUN set -eux; \
    sed -i 's|https\?://dl-cdn.alpinelinux.org/alpine|https://mirrors.cloud.tencent.com/alpine|g' /etc/apk/repositories; \
    apk add --no-cache bash ca-certificates curl git procps ripgrep util-linux

FROM ${HANDS_OS}-runtime

ARG ENVD_VERSION=0.6.13

RUN install -d -m 0755 /workspace /workspace/.ags /usr/share/doc/envd

COPY --from=envd-builder /out/envd /usr/bin/envd
COPY --from=envd-builder /out/LICENSE /usr/share/doc/envd/LICENSE
COPY contract.json /etc/ags-hands-contract.json

RUN set -eux; \
    test "$(/usr/bin/envd -version)" = "${ENVD_VERSION}"; \
    test -s /usr/share/doc/envd/LICENSE; \
    grep -q '"port": 49983' /etc/ags-hands-contract.json; \
    grep -q '"workspaceRoot": "/workspace"' /etc/ags-hands-contract.json

WORKDIR /workspace
USER root

EXPOSE 49983/tcp
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["curl", "--fail", "--silent", "http://127.0.0.1:49983/health"]

ENTRYPOINT ["/usr/bin/envd"]
CMD ["-port", "49983"]
