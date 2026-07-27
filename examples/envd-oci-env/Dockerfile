ARG GO_VERSION=1.25.9
ARG BASE_IMAGE=ubuntu:22.04

FROM golang:${GO_VERSION}-bookworm AS envd-builder

ARG ENVD_VERSION=0.5.14
WORKDIR /workspace
COPY utils/envd/versions/${ENVD_VERSION}/src ./src
COPY utils/envd/versions/${ENVD_VERSION}/shared ./shared

ARG ENVD_BUILD_REVISION=a3fb26e-execenv
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

ARG ENVD_VERSION=0.5.14
COPY --from=envd-builder /out/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd

# These values are intentionally baked into the OCI image. The validation
# proves whether envd passes them to commands started after the sandbox boots.
ENV EXEC_ENABLE_ALL_ENV=1
ENV ENVD_SOURCE_VERSION=${ENVD_VERSION}
ENV ENVD_IMAGE_ONLY=from-oci-image
ENV ENVD_OVERRIDE_ORDER=from-oci-image

USER root
WORKDIR /root
ENTRYPOINT ["/usr/bin/envd"]
