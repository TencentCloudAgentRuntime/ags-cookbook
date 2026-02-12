#!/usr/bin/env python3
"""AGS SandboxTool synchronization script.

This script syncs dataset images to AGS tools by:
1) Reading docker_image entries from the dataset
2) Converting them to TCR image references
3) Creating missing SandboxTools with envd configuration
4) Writing a mapping file: image -> tool_name -> tool_id

Usage:
    python scripts/ags_tool_sync.py --dataset R2E-Gym/SWE-Bench-Lite
    python scripts/ags_tool_sync.py --dataset R2E-Gym/SWE-Bench-Lite --check-only

Environment variables required:
    TENCENTCLOUD_SECRET_ID
    TENCENTCLOUD_SECRET_KEY

Optional:
    TENCENTCLOUD_ROLE_ARN
    AGS_REGION (default: ap-guangzhou)
    TCR_REGISTRY (default: ccr.ccs.tencentyun.com)
    SANDBOX_IMAGE_REGISTRY_TYPE (default: personal)
"""

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

try:
    from ags_tool import AGSRuntime
except ImportError:
    print("Error: ags_tool module required.")
    sys.exit(1)

try:
    from datasets import load_dataset
except ImportError:
    print("Error: datasets library required. Install with: pip install datasets")
    sys.exit(1)


ENVD_CONFIG = {
    "startup_command": "/bin/bash",
    "startup_args": "-c",
    "startup_script": "/mnt/envd -port 49983",
    "envd_port": 49983,
    "env_vars": [
        {"name": "LANG", "value": "en_US.UTF-8"},
        {
            "name": "PATH",
            "value": "/envd/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        },
        {"name": "DEBIAN_FRONTEND", "value": "noninteractive"},
        {"name": "PYTHONUNBUFFERED", "value": "1"},
    ],
    "envd_mount": {
        "mount_path": "/mnt/envd",
        "image_address": "ccr.ccs.tencentyun.com/archerlliu/envd:20260115_201017",
        "sub_path": "/usr/bin/envd",
    },
    "health_check": {"path": "/health", "port": 49983},
}


@dataclass
class AGSSyncConfig:
    secret_id: str
    secret_key: str
    region: str = "ap-guangzhou"
    role_arn: str = ""
    tcr_registry: str = "ccr.ccs.tencentyun.com"
    image_registry_type: str = "personal"

    @classmethod
    def from_env(cls) -> "AGSSyncConfig":
        secret_id = os.getenv("TENCENTCLOUD_SECRET_ID", "")
        secret_key = os.getenv("TENCENTCLOUD_SECRET_KEY", "")

        if not secret_id or not secret_key:
            raise ValueError(
                "TENCENTCLOUD_SECRET_ID and TENCENTCLOUD_SECRET_KEY are required. "
                "Set these environment variables before running this script."
            )

        return cls(
            secret_id=secret_id,
            secret_key=secret_key,
            region=os.getenv("AGS_REGION", "ap-guangzhou"),
            role_arn=os.getenv("TENCENTCLOUD_ROLE_ARN", ""),
            tcr_registry=os.getenv("TCR_REGISTRY", "ccr.ccs.tencentyun.com"),
            image_registry_type=os.getenv("SANDBOX_IMAGE_REGISTRY_TYPE", "personal"),
        )


def normalize_image(image: str) -> str:
    return image.replace("docker.io/", "")


def replace_registry(image: str, registry: str) -> str:
    image = normalize_image(image)
    parts = image.split("/")
    if len(parts) >= 3 and ("." in parts[0] or ":" in parts[0]):
        parts = parts[1:]
    return f"{registry}/" + "/".join(parts)


def build_tool_name(image: str) -> str:
    """Build a valid AGS tool name from a TCR image reference.

    Constraints: only letters, numbers, underscores, hyphens; max 50 chars.
    Strategy: <repo_part>-<tag>, truncating repo_part if needed to fit 50.
    Example: ccr.ccs.tencentyun.com/namanjain12/aiohttp_final:abcdef123
          -> aiohttp_final-abcdef123
    """
    import re

    MAX_LEN = 50

    # Strip registry prefix (e.g. ccr.ccs.tencentyun.com/)
    parts = image.split("/")
    if len(parts) >= 3 and ("." in parts[0] or ":" in parts[0]):
        repo_with_tag = "/".join(parts[1:])
    else:
        repo_with_tag = image

    # Split repo and tag (e.g. "namanjain12/aiohttp_final:abcdef123")
    if ":" in repo_with_tag:
        repo_part, tag = repo_with_tag.rsplit(":", 1)
    else:
        repo_part, tag = repo_with_tag, ""

    # Use only the last segment of the repo (e.g. "aiohttp_final")
    repo_name = repo_part.rsplit("/", 1)[-1]

    # Sanitize: replace invalid chars with hyphens
    repo_name = re.sub(r"[^a-zA-Z0-9_-]", "-", repo_name).strip("-")
    tag = re.sub(r"[^a-zA-Z0-9_-]", "-", tag).strip("-")

    if tag:
        # Reserve space for repo_name + "-" + tag
        max_repo = MAX_LEN - len(tag) - 1
        if max_repo < 1:
            # Tag alone exceeds limit; truncate tag
            name = tag[:MAX_LEN]
        else:
            name = f"{repo_name[:max_repo]}-{tag}"
    else:
        name = repo_name[:MAX_LEN]

    # Collapse consecutive hyphens and trim
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name


def get_ags_runtime(config: AGSSyncConfig) -> AGSRuntime:
    return AGSRuntime(
        secret_id=config.secret_id,
        secret_key=config.secret_key,
        region=config.region,
        role_arn=config.role_arn,
    )


def list_existing_tools(runtime: AGSRuntime) -> dict[str, str]:
    existing = {}
    offset = 0
    limit = 100

    while True:
        try:
            resp = runtime.list_tools(limit=limit, offset=offset)
            tools = resp.SandboxToolSet or []
            if not tools:
                break
            for tool in tools:
                existing[tool.ToolName] = tool.ToolId
            if len(tools) < limit:
                break
            offset += limit
        except Exception as e:
            print(f"Warning: Failed to list tools at offset {offset}: {e}")
            break

    return existing


def create_sandbox_tool(
    runtime: AGSRuntime,
    tool_name: str,
    docker_image: str,
    config: AGSSyncConfig,
    original_image: str = "",
    dry_run: bool = False,
) -> Optional[str]:
    if dry_run:
        print(f"  [DRY RUN] Would create tool: {tool_name}")
        print(f"            From image: {docker_image}")
        return None

    try:
        tool_id = runtime.create_tool(
            tool_name=tool_name,
            image=docker_image,
            image_registry_type=config.image_registry_type,
            tool_description=f"SWE sandbox for {docker_image}",
            command=[ENVD_CONFIG["startup_command"], ENVD_CONFIG["startup_args"]],
            command_args=[ENVD_CONFIG["startup_script"]],
            env_vars=ENVD_CONFIG["env_vars"],
            ports=[{"name": "envd", "port": ENVD_CONFIG["envd_port"], "protocol": "TCP"}],
            storage_mounts=[
                {
                    "name": "envd-storage",
                    "mount_path": ENVD_CONFIG["envd_mount"]["mount_path"],
                    "readonly": True,
                    "image": ENVD_CONFIG["envd_mount"]["image_address"],
                    "image_registry_type": "personal",
                    "subpath": ENVD_CONFIG["envd_mount"]["sub_path"],
                }
            ],
            probe_path=ENVD_CONFIG["health_check"]["path"],
            probe_port=ENVD_CONFIG["health_check"]["port"],
            probe_scheme="HTTP",
            probe_ready_timeout_ms=30000,
            probe_timeout_ms=1000,
            probe_period_ms=2000,
            probe_success_threshold=1,
            probe_failure_threshold=30,
            role_arn=config.role_arn,
            tags=[
                {"key": "image", "value": original_image or docker_image},
                {"key": "tcr_image", "value": docker_image},
            ],
        )
        print(f"  Created tool: {tool_name} -> {tool_id}")
        return tool_id
    except Exception as e:
        print(f"  Failed to create tool {tool_name}: {e}")
        return None


def load_mapping(path: str) -> dict[str, str | dict]:
    with open(path, "r") as f:
        return json.load(f)


def get_tcr_image(mapping_entry, registry: str) -> str:
    if isinstance(mapping_entry, str):
        return mapping_entry
    if isinstance(mapping_entry, dict):
        if "tcr_image" in mapping_entry:
            return mapping_entry["tcr_image"]
        if "image" in mapping_entry:
            return replace_registry(mapping_entry["image"], registry)
    raise ValueError("Invalid mapping entry")


def extract_images_from_dataset(dataset_name: str, split: str = "test") -> list[str]:
    print(f"Loading dataset: {dataset_name} (split: {split})")

    try:
        dataset = load_dataset(dataset_name, split=split)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return []

    images = set()
    for entry in dataset:
        image = entry.get("docker_image") or entry.get("image_name")
        if image:
            images.add(image)

    images = sorted(images)
    print(f"Found {len(images)} unique images in dataset")
    return images


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize Docker images to AGS SandboxTools"
    )
    parser.add_argument(
        "--mapping",
        type=str,
        default=None,
        help="Path to image->TCR mapping JSON (from push_to_tcr.py)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="R2E-Gym/SWE-Bench-Lite",
        help="HuggingFace dataset name (e.g., R2E-Gym/SWE-Bench-Lite)",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="test",
        help="Dataset split to use (default: test)",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check which tools need to be created, don't create them",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="tool_mapping.json",
        help="Output file for tool name mapping (default: tool_mapping.json)",
    )
    parser.add_argument(
        "--region",
        type=str,
        default=None,
        help="AGS region (default: from env or ap-guangzhou)",
    )
    parser.add_argument(
        "--registry",
        type=str,
        default=None,
        help="TCR registry (default: from env or ccr.ccs.tencentyun.com)",
    )

    args = parser.parse_args()

    try:
        config = AGSSyncConfig.from_env()
        if args.region:
            config.region = args.region
        if args.registry:
            config.tcr_registry = args.registry
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    mapping_data = None
    images = []
    if args.mapping:
        mapping_data = load_mapping(args.mapping)
        images = sorted(mapping_data.keys())
        if not images:
            print("No images found in mapping file")
            sys.exit(1)
    else:
        images = extract_images_from_dataset(args.dataset, args.split)
        if not images:
            print("No images found in dataset")
            sys.exit(1)

    print(f"\nConnecting to AGS (region: {config.region})...")
    runtime = get_ags_runtime(config)

    print("Fetching existing SandboxTools...")
    existing_tools = list_existing_tools(runtime)
    print(f"Found {len(existing_tools)} existing tools")

    tool_mapping: dict[str, dict[str, Optional[str]]] = {}
    missing_tools = []

    for image in images:
        tcr_image = (
            get_tcr_image(mapping_data[image], config.tcr_registry)
            if mapping_data
            else replace_registry(image, config.tcr_registry)
        )
        tool_name = build_tool_name(tcr_image)
        tool_mapping[image] = {
            "tool_name": tool_name,
            "tool_id": existing_tools.get(tool_name),
            "tcr_image": tcr_image,
        }

        if tool_name not in existing_tools:
            missing_tools.append((image, tool_name, tcr_image))

    print(f"\nTools to create: {len(missing_tools)}")
    print(f"Tools already exist: {len(images) - len(missing_tools)}")

    if args.check_only:
        print("\n[CHECK ONLY MODE]")
        if missing_tools:
            print("Missing tools:")
            for _image, tool_name, tcr_image in missing_tools:
                print(f"  - {tool_name} (image {tcr_image})")
        else:
            print("All tools already exist!")
    else:
        if missing_tools:
            print("\nCreating missing tools...")
            for image, tool_name, tcr_image in missing_tools:
                tool_id = create_sandbox_tool(
                    runtime, tool_name, tcr_image, config,
                    original_image=image,
                )
                if tool_id:
                    tool_mapping[image]["tool_id"] = tool_id

    print(f"\nSaving tool mapping to {args.output}...")
    with open(args.output, "w") as f:
        json.dump(tool_mapping, f, indent=2)
    print("Done!")


if __name__ == "__main__":
    main()
