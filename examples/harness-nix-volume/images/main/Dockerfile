FROM ubuntu:22.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/sh", "-lc", "sleep infinity"]
