#!/usr/bin/env python3
"""Pull images from a dataset and push them to a TCR registry.

Usage:
    python scripts/push_to_tcr.py --dataset R2E-Gym/SWE-Bench-Lite --registry ccr.ccs.tencentyun.com

Environment variables:
    TCR_USERNAME / TCR_PASSWORD: credentials for docker login (optional)
    USE_SUDO: set to "1" to prefix docker commands with sudo

Notes:
    - This script only rewrites the registry; repository and tag stay the same.
    - Example: docker.io/slimshetty/swebench-lite:tag -> ccr.ccs.tencentyun.com/slimshetty/swebench-lite:tag
"""

import argparse
import os
import subprocess
import sys
from typing import Iterable, List, Tuple

try:
    from datasets import load_dataset
except ImportError as exc:
    sys.stderr.write("datasets package required. Install with: pip install datasets\n")
    raise


# ---------------------------- helpers ----------------------------


def docker_cmd(base: List[str], use_sudo: bool) -> List[str]:
    return (["sudo"] if use_sudo else []) + ["docker"] + base


def run(cmd: List[str], use_sudo: bool, **kwargs):
    full_cmd = docker_cmd(cmd, use_sudo)
    print("$", " ".join(full_cmd))
    subprocess.run(full_cmd, check=True, **kwargs)


def strip_registry(image: str) -> str:
    """Remove registry prefix if present (keep repo:tag)."""
    parts = image.split("/")
    if len(parts) >= 3 and ("." in parts[0] or ":" in parts[0] or parts[0] == "docker.io"):
        return "/".join(parts[1:])
    return image


def to_tcr_image(image: str, registry: str) -> str:
    return f"{registry}/{strip_registry(image)}"


def login_if_needed(registry: str, use_sudo: bool, username: str | None, password: str | None):
    if not username or not password:
        print("Skipping docker login (no credentials). Set TCR_USERNAME/TCR_PASSWORD to login automatically.")
        return
    run(["login", registry, "-u", username, "-p", password], use_sudo)


def load_images(dataset: str, split: str | None, trust_remote_code: bool, streaming: bool) -> List[str]:
    def collect_from(ds_list):
        images = set()
        for ds in ds_list:
            for row in ds:
                image = None
                if isinstance(row, str):
                    image = row
                elif isinstance(row, dict):
                    image = row.get("docker_image") or row.get("image_name") or row.get("image")
                else:
                    try:
                        image = row.get("docker_image") or row.get("image_name")
                    except Exception:
                        image = None
                if image:
                    images.add(image)
        images = sorted(images)
        print(f"Found {len(images)} unique images")
        return images

    def _build_kwargs():
        """Only pass optional flags when explicitly enabled, matching the
        behaviour of plain ``load_dataset(name)``."""
        kwargs = {}
        if trust_remote_code:
            kwargs["trust_remote_code"] = True
        if streaming:
            kwargs["streaming"] = True
        return kwargs

    print(f"Loading dataset {dataset}...")
    kwargs = _build_kwargs()

    # Strategy 1: load as DatasetDict – same style as prepare_swe_data.py
    try:
        ds_dict = load_dataset(dataset, **kwargs)
        if hasattr(ds_dict, "keys") and len(ds_dict) > 0:
            if split and split in ds_dict:
                return collect_from([ds_dict[split]])
            return collect_from([ds_dict[k] for k in ds_dict.keys()])
    except Exception as exc:
        print(f"  load_dataset({dataset}) failed: {exc}")

    # Strategy 2: load with specific split names
    datasets = []
    targets = [split] if split else ["train", "test", "validation", "dev"]
    for cand in targets:
        try:
            datasets.append(load_dataset(dataset, split=cand, **kwargs))
        except Exception:
            continue
    if datasets:
        return collect_from(datasets)

    raise RuntimeError(f"No readable splits found for {dataset}")

def push_images(images: Iterable[str], registry: str, use_sudo: bool, dry_run: bool = False) -> List[Tuple[str, str]]:
    mapping = []
    for idx, image in enumerate(images, 1):
        tcr_image = to_tcr_image(image, registry)
        print(f"[{idx}/{len(images)}] {image} -> {tcr_image}")
        mapping.append((image, tcr_image))

        if dry_run:
            continue

        try:
            run(["pull", image], use_sudo)
            run(["tag", image, tcr_image], use_sudo)
            run(["push", tcr_image], use_sudo)
        except subprocess.CalledProcessError as exc:
            print(f"Failed to push {image} -> {tcr_image}: {exc}")
    return mapping


# ---------------------------- main ----------------------------


def main():
    parser = argparse.ArgumentParser(description="Push dataset images to TCR")
    parser.add_argument("--dataset", default="R2E-Gym/SWE-Bench-Lite", help="HF dataset containing docker_image/image_name")
    parser.add_argument("--split", default="all", help="Dataset split (use all for every split)")
    parser.add_argument("--trust-remote-code", action="store_true", help="Enable trust_remote_code for HF datasets")
    parser.add_argument("--streaming", action="store_true", help="Use HF streaming mode")
    parser.add_argument("--registry", default=os.getenv("TCR_REGISTRY", "ccr.ccs.tencentyun.com"), help="Target TCR registry")
    parser.add_argument("--dry-run", action="store_true", help="Do not run docker commands")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of images (for testing)")
    args = parser.parse_args()

    use_sudo = os.getenv("USE_SUDO", "0") == "1"
    username = os.getenv("TCR_USERNAME")
    password = os.getenv("TCR_PASSWORD")

    split = None if args.split == "all" else args.split
    trust_remote = args.trust_remote_code
    images = load_images(args.dataset, split, trust_remote, streaming=args.streaming)
    if args.limit:
        images = images[: args.limit]

    login_if_needed(args.registry, use_sudo, username, password)
    mapping = push_images(images, args.registry, use_sudo, dry_run=args.dry_run)

    out_path = os.getenv("TCR_MAPPING_OUT", "tcr_image_mapping.json")
    with open(out_path, "w") as f:
        import json
        json.dump({src: dst for src, dst in mapping}, f, indent=2)
    print(f"Saved mapping to {out_path}")


if __name__ == "__main__":
    main()
