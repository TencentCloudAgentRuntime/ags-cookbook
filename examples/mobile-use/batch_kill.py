#!/usr/bin/env python3
"""
Batch kill sandboxes by ID list with concurrency control.

Usage:
    # Kill from command line arguments
    python batch_kill.py sandbox_id_1 sandbox_id_2 sandbox_id_3 ...

    # Kill from a text file (one sandbox ID per line)
    python batch_kill.py --file sandbox_ids.txt

    # Kill from a CSV file (auto-detects 'instance_id' or first column)
    python batch_kill.py --csv sandhub_sql_result_20260424211013.csv

    # Customize concurrency (default 50)
    python batch_kill.py --concurrency 20 sandbox_id_1 sandbox_id_2

    # Customize sleep interval between batches in seconds (default 1)
    python batch_kill.py --sleep 2 sandbox_id_1 sandbox_id_2

Requires E2B_API_KEY and E2B_DOMAIN in environment or .env file.
"""

import os
import sys
import csv
import time
import asyncio
import argparse
from pathlib import Path
from typing import List, Tuple


def _load_env_file() -> None:
    """Load .env file from script directory."""
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.absolute() / ".env")
    except ImportError:
        env_file = Path(__file__).parent.absolute() / ".env"
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch kill sandboxes by ID")
    parser.add_argument("sandbox_ids", nargs="*", help="Sandbox IDs to kill")
    parser.add_argument("--file", "-f", type=str, help="Text file with sandbox IDs (one per line)")
    parser.add_argument("--csv", type=str, help="CSV file with sandbox IDs (auto-detects 'instance_id' or uses first column)")
    parser.add_argument("--concurrency", "-c", type=int, default=50, help="Concurrency per batch (default: 50)")
    parser.add_argument("--sleep", "-s", type=float, default=1.0, help="Sleep seconds between batches (default: 1.0)")
    args = parser.parse_args()

    # Collect sandbox IDs
    sandbox_ids: List[str] = []

    if args.csv:
        csv_path = Path(args.csv)
        if not csv_path.exists():
            print(f"Error: CSV file not found: {args.csv}", file=sys.stderr)
            sys.exit(1)
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            # Try 'instance_id' column, fallback to first column
            fieldnames = reader.fieldnames or []
            if 'instance_id' in fieldnames:
                col = 'instance_id'
            elif fieldnames:
                col = fieldnames[0]
            else:
                print(f"Error: CSV file has no columns", file=sys.stderr)
                sys.exit(1)
            print(f"Reading column '{col}' from {args.csv}")
            for row in reader:
                val = row.get(col, '').strip()
                if val:
                    sandbox_ids.append(val)

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    sandbox_ids.append(line)

    sandbox_ids.extend(args.sandbox_ids)

    if not sandbox_ids:
        print("Error: no sandbox IDs provided. Use positional args or --file.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for sid in sandbox_ids:
        if sid not in seen:
            seen.add(sid)
            unique_ids.append(sid)
    sandbox_ids = unique_ids

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
    print()

    success, fail = asyncio.run(kill_batch(sandbox_ids, concurrency=args.concurrency, sleep_interval=args.sleep))
    sys.exit(1 if fail > 0 else 0)


if __name__ == "__main__":
    main()
