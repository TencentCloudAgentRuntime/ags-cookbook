#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "images" / "claude-code-volume" / "Dockerfile"


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

    if not DOCKERFILE.is_file():
        raise SystemExit(f"volume Dockerfile is missing: {DOCKERFILE}")

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
        str(DOCKERFILE),
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
