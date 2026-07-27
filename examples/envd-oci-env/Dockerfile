ARG GO_IMAGE=golang:1.26.5-bookworm
ARG BASE_IMAGE=ubuntu:22.04

FROM ${GO_IMAGE} AS envd-builder

WORKDIR /workspace
COPY utils/envd/src ./src
COPY utils/envd/shared ./shared

ARG ENVD_BUILD_REVISION=7c23f7b-execenv
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

COPY --from=envd-builder /out/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd

# These values are intentionally baked into the OCI image. The validation
# proves whether envd passes them to commands started after the sandbox boots.
ENV ENVD_IMAGE_ONLY=from-oci-image
ENV ENVD_OVERRIDE_ORDER=from-oci-image

USER root
WORKDIR /root
ENTRYPOINT ["/usr/bin/envd"]
