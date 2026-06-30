#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

CONTAINER_ENGINE="${CONTAINER_ENGINE:-podman}"
IMAGE_PLATFORM="${IMAGE_PLATFORM:-linux/amd64}"
TARGET="${1:-all}"

need_engine() {
  command -v "$CONTAINER_ENGINE" >/dev/null 2>&1 || {
    echo "missing container engine: $CONTAINER_ENGINE" >&2
    exit 2
  }
}

build_main() {
  local image_ref tmpdir
  image_ref="${MAIN_IMAGE_REF:-${RUNTIME_IMAGE_REF:-}}"
  image_ref="${image_ref:?MAIN_IMAGE_REF is required}"
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' RETURN
  cp "$ROOT_DIR/images/main/Dockerfile" "$tmpdir/Dockerfile"
  "$CONTAINER_ENGINE" build --platform "$IMAGE_PLATFORM" -f "$tmpdir/Dockerfile" -t "$image_ref" "$tmpdir"
  "$CONTAINER_ENGINE" push "$image_ref"
  echo "MAIN_IMAGE_PUSHED=$image_ref"
}

build_tunnel() {
  local image_ref tmpdir bin_path
  image_ref="${TUNNEL_IMAGE_REF:?TUNNEL_IMAGE_REF is required}"
  command -v go >/dev/null 2>&1 || {
    echo "missing command: go" >&2
    exit 2
  }
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' RETURN
  mkdir -p "$tmpdir/tunnel/bin"
  bin_path="$tmpdir/tunnel/bin/ags-tunnel-server"
  (
    cd "$ROOT_DIR/tunnel/server"
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o "$bin_path" ./cmd/ags-tunnel-server
  )
  chmod 0755 "$tmpdir/tunnel/bin/ags-tunnel-server"
  "$CONTAINER_ENGINE" build --platform "$IMAGE_PLATFORM" -f "$ROOT_DIR/images/tunnel/Dockerfile" -t "$image_ref" "$tmpdir"
  "$CONTAINER_ENGINE" push "$image_ref"
  echo "TUNNEL_IMAGE_PUSHED=$image_ref"
}

build_workload() {
  local image_ref tmpdir claude_code_dir
  image_ref="${WORKLOAD_IMAGE_REF:?WORKLOAD_IMAGE_REF is required}"
  claude_code_dir="${CLAUDE_CODE_DIR:-$ROOT_DIR/dist/claude-code-linux-amd64/claude-code}"
  test -x "$claude_code_dir/bin/claude" || {
    echo "CLAUDE_CODE_DIR does not contain executable bin/claude: $claude_code_dir" >&2
    echo "run ./scripts/build-claude-code-dir.sh first, or set CLAUDE_CODE_DIR explicitly" >&2
    exit 2
  }
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' RETURN
  mkdir -p "$tmpdir/claude-code"
  cp -R "$claude_code_dir"/. "$tmpdir/claude-code/"
  chmod -R a+rX "$tmpdir/claude-code"
  "$CONTAINER_ENGINE" build --platform "$IMAGE_PLATFORM" -f "$ROOT_DIR/images/demo-workload/Dockerfile" -t "$image_ref" "$tmpdir"
  "$CONTAINER_ENGINE" push "$image_ref"
  echo "WORKLOAD_IMAGE_PUSHED=$image_ref"
}

need_engine
case "$TARGET" in
  main|runtime) build_main ;;
  tunnel) build_tunnel ;;
  workload) build_workload ;;
  all)
    build_main
    build_tunnel
    build_workload
    ;;
  *)
    echo "usage: $0 [main|tunnel|workload|all]" >&2
    exit 2
    ;;
esac
