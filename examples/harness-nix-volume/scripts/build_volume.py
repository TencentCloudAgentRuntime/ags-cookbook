#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "dist" / "claude-code-volume"

DOCKERFILE = """\
ARG NIX_BUILDER_IMAGE=nixos/nix:2.26.3
FROM ${NIX_BUILDER_IMAGE} AS builder

WORKDIR /src
RUN mkdir -p /etc/nix \\
    && printf 'experimental-features = nix-command flakes\\naccept-flake-config = true\\nsandbox = false\\nfilter-syscalls = false\\n' > /etc/nix/nix.conf

COPY nix/ /src/nix/
RUN nix-build /src/nix/default.nix --out-link /tmp/claude-code-result \\
    && result_path="$(readlink -f /tmp/claude-code-result)" \\
    && mkdir -p /nix-export/nix/store /nix-export/nix/claude-code \\
    && cp -a $(nix-store -qR /tmp/claude-code-result) /nix-export/nix/store/ \\
    && ln -s "$result_path" /nix-export/nix/claude-code/nix-env

FROM scratch
COPY --from=builder /nix-export/ /
"""


def need(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> int:
    engine = os.getenv("CONTAINER_ENGINE", "docker")
    if shutil.which(engine) is None:
        raise SystemExit(f"{engine} is required to build the image")

    image_ref = need("CLAUDE_CODE_VOLUME_IMAGE_REF")
    platform = os.getenv("IMAGE_PLATFORM", "linux/amd64")
    builder = os.getenv("NIX_BUILDER_IMAGE", "nixos/nix:2.26.3")

    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    BUILD_DIR.mkdir(parents=True)
    dockerfile = BUILD_DIR / "Dockerfile"
    dockerfile.write_text(DOCKERFILE, encoding="utf-8")

    command = [
        engine,
        "build",
        "--platform",
        platform,
        "--build-arg",
        f"NIX_BUILDER_IMAGE={builder}",
        "-t",
        image_ref,
        "-f",
        str(dockerfile),
    ]
    if security_opt := os.getenv("CONTAINER_BUILD_SECURITY_OPT"):
        command.extend(["--security-opt", security_opt])
    command.append(str(ROOT))
    subprocess.run(command, check=True)

    print(f"Built Claude Code image volume: {image_ref}")
    print("Run 'make push-images' before 'make run' so AGS can pull both images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
