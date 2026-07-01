#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="${CONTAINER_ENGINE:-docker}"
PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
IMAGE_REF="${HARNESS_VOLUME_IMAGE_REF:?set HARNESS_VOLUME_IMAGE_REF in .env}"
BUILD_DIR="$ROOT_DIR/dist/harness-volume"
NIX_BUILDER_IMAGE="${NIX_BUILDER_IMAGE:-nixos/nix:2.26.3}"
BUILD_SECURITY_OPT="${CONTAINER_BUILD_SECURITY_OPT:-}"

command -v "$ENGINE" >/dev/null 2>&1 || {
  echo "$ENGINE is required to build the image" >&2
  exit 1
}

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

cat > "$BUILD_DIR/Dockerfile" <<'DOCKERFILE'
ARG NIX_BUILDER_IMAGE=nixos/nix:2.26.3
FROM ${NIX_BUILDER_IMAGE} AS builder

WORKDIR /src
RUN mkdir -p /etc/nix \
    && printf 'experimental-features = nix-command flakes\naccept-flake-config = true\nsandbox = false\nfilter-syscalls = false\n' > /etc/nix/nix.conf

COPY nix/ /src/nix/
RUN nix-build /src/nix/default.nix --out-link /tmp/harness-result \
    && result_path="$(readlink -f /tmp/harness-result)" \
    && mkdir -p /nix-export/nix/store /nix-export/nix/harness \
    && cp -a $(nix-store -qR /tmp/harness-result) /nix-export/nix/store/ \
    && ln -s "$result_path" /nix-export/nix/harness/nix-env

FROM scratch
COPY --from=builder /nix-export/ /
DOCKERFILE

build_args=(
  --platform "$PLATFORM"
  --build-arg "NIX_BUILDER_IMAGE=$NIX_BUILDER_IMAGE"
  -t "$IMAGE_REF"
  -f "$BUILD_DIR/Dockerfile"
)
if [[ -n "$BUILD_SECURITY_OPT" ]]; then
  build_args+=(--security-opt "$BUILD_SECURITY_OPT")
fi

"$ENGINE" build "${build_args[@]}" "$ROOT_DIR"

echo "Built Harness image volume: $IMAGE_REF"
echo "Push it before running make run, for example:"
echo "  $ENGINE push $IMAGE_REF"
