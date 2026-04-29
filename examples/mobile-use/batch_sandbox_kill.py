#!/usr/bin/env python3
"""
Batch kill sandboxes by ID list with concurrency control.

Reads sandbox IDs from a YAML config file (default: sandboxes.yaml),
asks for manual confirmation before executing, then kills all listed sandboxes.

Usage:
    # Kill sandboxes listed in default sandboxes.yaml
    python batch_sandbox_kill.py

    # Kill sandboxes from a specific YAML config
    python batch_sandbox_kill.py --config my_sandboxes.yaml

    # Customize concurrency (default 50)
    python batch_sandbox_kill.py --concurrency 20

    # Customize sleep interval between batches in seconds (default 1)
    python batch_sandbox_kill.py --sleep 2

    # Skip confirmation prompt
    python batch_sandbox_kill.py --yes

YAML config format:
    sandbox_ids:
      - sandbox_id_1
      - sandbox_id_2
      - sandbox_id_3

Requires E2B_API_KEY and E2B_DOMAIN in environment or .env file.
"""

import os
import sys
import time
import asyncio
import argparse
from pathlib import Path
from typing import List, Tuple

# Script directory
SCRIPT_DIR = Path(__file__).parent


def _load_env_file() -> None:
    """Load .env file from script directory."""
    try:
        from dotenv import load_dotenv
        load_dotenv(SCRIPT_DIR / ".env")
    except ImportError:
        env_file = SCRIPT_DIR / ".env"
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()


def load_sandbox_ids_from_yaml(yaml_path: str) -> List[str]:
    """Load sandbox IDs from a YAML config file.

    Expected YAML format:
        sandbox_ids:
          - sandbox_id_1
          - sandbox_id_2

    Args:
        yaml_path: Path to the YAML file.

    Returns:
        Deduplicated list of sandbox IDs.
    """
    import yaml

    config_path = Path(yaml_path)
    if not config_path.exists():
        print(f"Error: YAML config file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        print(f"Error: YAML root must be a mapping, got {type(config).__name__}", file=sys.stderr)
        sys.exit(1)

    raw_ids = config.get('sandbox_ids', [])
    if not isinstance(raw_ids, list):
        print(f"Error: 'sandbox_ids' must be a list, got {type(raw_ids).__name__}", file=sys.stderr)
        sys.exit(1)

    # Convert to strings, strip whitespace, skip empty
    sandbox_ids: List[str] = []
    for item in raw_ids:
        sid = str(item).strip()
        if sid:
            sandbox_ids.append(sid)

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for sid in sandbox_ids:
        if sid not in seen:
            seen.add(sid)
            unique_ids.append(sid)

    print(f"Loaded {len(unique_ids)} sandbox IDs from {yaml_path}")
    return unique_ids


async def kill_batch(sandbox_ids: List[str], concurrency: int = 50, sleep_interval: float = 2.0) -> Tuple[int, int]:
    """
    Kill sandboxes in batches with concurrency control.

    Args:
        sandbox_ids: List of sandbox IDs to kill.
        concurrency: Max concurrent kills per batch.
        sleep_interval: Sleep seconds between batches.

    Returns:
        Tuple of (success_count, fail_count).
    """
    from e2b import AsyncSandbox

    total = len(sandbox_ids)
    success_count = 0
    fail_count = 0
    not_found_count = 0

    total_batches = (total + concurrency - 1) // concurrency
    print(f"Total sandboxes: {total}, concurrency: {concurrency}, batches: {total_batches}")
    print(f"Sleep between batches: {sleep_interval}s")
    print()

    for batch_idx in range(total_batches):
        start = batch_idx * concurrency
        end = min(start + concurrency, total)
        batch = sandbox_ids[start:end]

        print(f"[Batch {batch_idx + 1}/{total_batches}] Killing {len(batch)} sandboxes ({start+1}-{end}/{total})...")
        batch_start = time.perf_counter()

        async def _kill_one(sid: str) -> Tuple[str, bool, str]:
            try:
                result = await AsyncSandbox.kill(sid)
                if result:
                    return (sid, True, "killed")
                else:
                    return (sid, True, "not_found")  # 404 = already gone, treat as success
            except Exception as e:
                return (sid, False, str(e)[:120])

        results = await asyncio.gather(*[_kill_one(sid) for sid in batch])

        batch_success = 0
        batch_fail = 0
        batch_not_found = 0
        for sid, ok, msg in results:
            if ok:
                batch_success += 1
                if msg == "not_found":
                    batch_not_found += 1
            else:
                batch_fail += 1
                print(f"  FAILED: {sid} - {msg}")

        success_count += batch_success
        fail_count += batch_fail
        not_found_count += batch_not_found

        elapsed_ms = (time.perf_counter() - batch_start) * 1000
        print(f"  Done: {batch_success} killed ({batch_not_found} not found), {batch_fail} failed, {elapsed_ms:.0f}ms")

        # Sleep between batches (skip after last batch)
        if batch_idx < total_batches - 1:
            await asyncio.sleep(sleep_interval)

    print()
    print(f"{'='*60}")
    print(f"Summary: {success_count} success ({not_found_count} not found), {fail_count} failed, {total} total")
    print(f"{'='*60}")

    return success_count, fail_count


def confirm_kill(sandbox_ids: List[str]) -> bool:
    """Show sandbox list and ask for manual confirmation.

    Args:
        sandbox_ids: List of sandbox IDs to be killed.

    Returns:
        True if user confirmed, False otherwise.
    """
    print()
    print("The following sandboxes will be KILLED:")
    print("-" * 60)
    for i, sid in enumerate(sandbox_ids, 1):
        print(f"  {i:4d}. {sid}")
    print("-" * 60)
    print(f"Total: {len(sandbox_ids)} sandboxes")
    print()

    try:
        answer = input("Are you sure you want to kill all of them? (y/yes to confirm, n/no to cancel): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        return False

    return answer in ('y', 'yes')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch kill sandboxes by ID from YAML config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
YAML config format:
    sandbox_ids:
      - sandbox_id_1
      - sandbox_id_2

Usage examples:
    %(prog)s
    %(prog)s --config my_sandboxes.yaml
    %(prog)s --concurrency 20 --sleep 2
    %(prog)s --yes
        """,
    )
    parser.add_argument("--config", type=str, default=str(SCRIPT_DIR / "sandboxes.yaml"),
                        help="YAML config file containing sandbox_ids list (default: sandboxes.yaml)")
    parser.add_argument("--concurrency", "-c", type=int, default=50, help="Concurrency per batch (default: 50)")
    parser.add_argument("--sleep", "-s", type=float, default=1.0, help="Sleep seconds between batches (default: 1.0)")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    # Load sandbox IDs from YAML
    sandbox_ids = load_sandbox_ids_from_yaml(args.config)

    if not sandbox_ids:
        print("Error: no sandbox IDs found in YAML config file.", file=sys.stderr)
        sys.exit(1)

    # Load env
    _load_env_file()

    domain = os.getenv("E2B_DOMAIN", "")
    api_key = os.getenv("E2B_API_KEY", "")

    if not domain:
        print("Error: E2B_DOMAIN not set", file=sys.stderr)
        sys.exit(1)
    if not api_key:
        print("Error: E2B_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    os.environ["E2B_DOMAIN"] = domain
    os.environ["E2B_API_KEY"] = api_key

    print(f"E2B_DOMAIN: {domain}")

    # Confirmation
    if not args.yes:
        if not confirm_kill(sandbox_ids):
            print("Cancelled.")
            sys.exit(0)
    print()

    success, fail = asyncio.run(kill_batch(sandbox_ids, concurrency=args.concurrency, sleep_interval=args.sleep))
    sys.exit(1 if fail > 0 else 0)


if __name__ == "__main__":
    main()
