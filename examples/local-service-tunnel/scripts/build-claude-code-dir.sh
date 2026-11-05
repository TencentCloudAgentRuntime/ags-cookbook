#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${DIST_DIR:-$ROOT_DIR/dist}"

TARGET_ARCH="${TARGET_ARCH:-amd64}"
UBUNTU_BASE="${UBUNTU_BASE:-22.04}"
NODE_MAJOR="${NODE_MAJOR:-22}"
CLAUDE_CODE_VERSION="${CLAUDE_CODE_VERSION:-latest}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-}"

case "$TARGET_ARCH" in
  amd64)
    PLATFORM="linux/amd64"
    NODE_ARCH="x64"
    EXPECTED_FILE_ARCH="x86-64"
    ;;
  arm64)
    PLATFORM="linux/arm64"
    NODE_ARCH="arm64"
    EXPECTED_FILE_ARCH="aarch64|ARM aarch64"
    ;;
  *)
    echo "unsupported TARGET_ARCH=$TARGET_ARCH" >&2
    exit 2
    ;;
esac

if [ -z "$CONTAINER_ENGINE" ]; then
  if command -v podman >/dev/null 2>&1; then
    CONTAINER_ENGINE=podman
  elif command -v docker >/dev/null 2>&1; then
    CONTAINER_ENGINE=docker
  else
    echo "podman or docker is required" >&2
    exit 2
  fi
fi

mkdir -p "$DIST_DIR"

"$CONTAINER_ENGINE" run --rm \
  --platform "$PLATFORM" \
  -e TARGET_ARCH="$TARGET_ARCH" \
  -e NODE_MAJOR="$NODE_MAJOR" \
  -e NODE_ARCH="$NODE_ARCH" \
  -e CLAUDE_CODE_VERSION="$CLAUDE_CODE_VERSION" \
  -e EXPECTED_FILE_ARCH="$EXPECTED_FILE_ARCH" \
  -v "$ROOT_DIR:/work" \
  -w /work \
  "docker.io/library/ubuntu:$UBUNTU_BASE" \
  bash -lc '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl file findutils jq tar xz-utils

node_version="$(curl -fsSL https://nodejs.org/dist/index.json | jq -r --arg major "v${NODE_MAJOR}." "[.[] | select(.version | startswith(\$major))][0].version")"
if [ -z "$node_version" ] || [ "$node_version" = null ]; then
  echo "could not resolve latest Node $NODE_MAJOR version" >&2
  exit 1
fi
curl -fsSL -o /tmp/node.tar.xz "https://nodejs.org/dist/${node_version}/node-${node_version}-linux-${NODE_ARCH}.tar.xz"
rm -rf /tmp/node
mkdir -p /tmp/node
tar -xJf /tmp/node.tar.xz -C /tmp/node --strip-components 1
export PATH="/tmp/node/bin:$PATH"
node --version
npm --version

rm -rf .claude-code-build/claude-code .claude-code-build/npm-prefix
mkdir -p .claude-code-build/claude-code/{bin,claude/bin} .claude-code-build/npm-prefix dist

npm_spec="@anthropic-ai/claude-code"
if [ "$CLAUDE_CODE_VERSION" != "latest" ]; then
  npm_spec="${npm_spec}@${CLAUDE_CODE_VERSION}"
fi
npm install --global --prefix .claude-code-build/npm-prefix "$npm_spec"

claude_cmd=".claude-code-build/npm-prefix/bin/claude"
if [ ! -e "$claude_cmd" ]; then
  echo "claude command was not installed at $claude_cmd" >&2
  exit 1
fi
claude_real="$(readlink -f "$claude_cmd")"
if ! file "$claude_real" | grep -Eq "ELF.*(${EXPECTED_FILE_ARCH})"; then
  claude_real="$(find .claude-code-build/npm-prefix -type f -perm -111 -print0 \
    | xargs -0 file \
    | awk -F: "/ELF/ && /(${EXPECTED_FILE_ARCH})/ && /claude/ {print \$1; exit}")"
fi
if [ -z "${claude_real:-}" ] || ! file "$claude_real" | grep -Eq "ELF.*(${EXPECTED_FILE_ARCH})"; then
  echo "could not find Linux ELF claude binary under npm prefix" >&2
  find .claude-code-build/npm-prefix -maxdepth 6 -type f -perm -111 -exec file {} \; >&2 || true
  exit 1
fi
install -m 0755 "$claude_real" .claude-code-build/claude-code/claude/bin/claude

cat > .claude-code-build/claude-code/bin/claude <<'"'"'EOF'"'"'
#!/bin/sh
set -eu
SELF="$0"
BIN_DIR="$(CDPATH= cd -- "$(dirname -- "$SELF")" && pwd)"
CLAUDE_CODE_HOME="${CLAUDE_CODE_HOME:-$(CDPATH= cd -- "$BIN_DIR/.." && pwd)}"
export CLAUDE_CONFIG_DIR="${CLAUDE_CONFIG_DIR:-/tmp/claude-config-${USER:-sandbox}}"
export DISABLE_AUTOUPDATER=1
export DISABLE_UPDATES=1
mkdir -p "$CLAUDE_CONFIG_DIR"
exec "$CLAUDE_CODE_HOME/claude/bin/claude" "$@"
EOF
chmod 0755 .claude-code-build/claude-code/bin/claude

.claude-code-build/claude-code/bin/claude --version
{
  echo "target_arch=$TARGET_ARCH"
  echo "ubuntu_base=22.04"
  echo "claude_version=$(.claude-code-build/claude-code/bin/claude --version 2>&1)"
  echo "built_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > .claude-code-build/claude-code/VERSION

(cd .claude-code-build/claude-code && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum) \
  > .claude-code-build/claude-code/MANIFEST.sha256

rm -rf "dist/claude-code-linux-${TARGET_ARCH}"
mkdir -p "dist/claude-code-linux-${TARGET_ARCH}"
cp -a .claude-code-build/claude-code "dist/claude-code-linux-${TARGET_ARCH}/claude-code"
'

echo "CLAUDE_CODE_DIR=$DIST_DIR/claude-code-linux-$TARGET_ARCH/claude-code"
