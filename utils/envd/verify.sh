#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
expected="$(awk '$2 == "envd" {print $1}' "$script_dir/SHA256SUMS")"

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$script_dir/envd" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$script_dir/envd" | awk '{print $1}')"
else
  echo "sha256sum or shasum is required" >&2
  exit 1
fi

if [[ "$actual" != "$expected" ]]; then
  echo "envd checksum mismatch" >&2
  echo "expected: $expected" >&2
  echo "actual:   $actual" >&2
  exit 1
fi

echo "envd checksum verified: $actual"
