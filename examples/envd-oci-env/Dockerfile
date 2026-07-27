ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

COPY utils/envd/envd /usr/bin/envd
RUN chmod 0755 /usr/bin/envd

# These values are intentionally baked into the OCI image. The validation
# proves whether envd passes them to commands started after the sandbox boots.
ENV ENVD_IMAGE_ONLY=from-oci-image
ENV ENVD_OVERRIDE_ORDER=from-oci-image

USER root
WORKDIR /root
ENTRYPOINT ["/usr/bin/envd"]
