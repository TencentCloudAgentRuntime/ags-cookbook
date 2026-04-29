#!/usr/bin/env python3
"""
One-time script: batch create 1500 sandboxes (create only, no operations).

Hardcoded:
    - Total: 1500
    - Concurrency: 25
    - Sleep between batches: 5s

Requires E2B_API_KEY, E2B_DOMAIN, SANDBOX_TEMPLATE in .env file.
"""

from __future__ import annotations

import os

os.environ.setdefault("E2B_MAX_KEEPALIVE_CONNECTIONS", "1000")
os.environ.setdefault("E2B_MAX_CONNECTIONS", "2000")

import sys
import time
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple

# ── Hardcoded config ──────────────────────────────────────────────
TOTAL = 10
CONCURRENCY = 5
SLEEP_INTERVAL = 10
# ──────────────────────────────────────────────────────────────────


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


def format_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


async def batch_create(
    total: int,
    concurrency: int,
    sleep_interval: float,
    template: str,
    timeout: int,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    from e2b import AsyncSandbox

    total_batches = (total + concurrency - 1) // concurrency
    created_ids: List[str] = []
    results: List[Dict[str, Any]] = []
    success_count = 0
    fail_count = 0

    print(f"Total to create: {total}")
    print(f"Concurrency: {concurrency}")
    print(f"Batches: {total_batches}")
    print(f"Sleep between batches: {sleep_interval}s")
    print(f"Template: {template}")
    print(f"Timeout: {timeout}s")
    print()

    overall_start = time.perf_counter()

    for batch_idx in range(total_batches):
        batch_start_idx = batch_idx * concurrency
        batch_end_idx = min(batch_start_idx + concurrency, total)
        batch_size = batch_end_idx - batch_start_idx

        print(f"[Batch {batch_idx + 1}/{total_batches}] Creating {batch_size} sandboxes "
              f"({batch_start_idx + 1}-{batch_end_idx}/{total})...")
        batch_start = time.perf_counter()

        async def _create_one(idx: int) -> Dict[str, Any]:
            start = time.perf_counter()
            try:
                sandbox = await AsyncSandbox.create(template=template, timeout=timeout)
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    'index': idx,
                    'sandbox_id': sandbox.sandbox_id,
                    'success': True,
                    'elapsed_ms': round(elapsed_ms, 1),
                    'error': '',
                    'timestamp': format_timestamp(),
                }
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return {
                    'index': idx,
                    'sandbox_id': '',
                    'success': False,
                    'elapsed_ms': round(elapsed_ms, 1),
                    'error': str(e)[:200],
                    'timestamp': format_timestamp(),
                }

        batch_results = await asyncio.gather(
            *[_create_one(batch_start_idx + i) for i in range(batch_size)]
        )

        batch_success = 0
        batch_fail = 0
        latencies = []
        for r in batch_results:
            results.append(r)
            if r['success']:
                batch_success += 1
                created_ids.append(r['sandbox_id'])
                latencies.append(r['elapsed_ms'])
            else:
                batch_fail += 1
                print(f"  FAILED [{r['index']}]: {r['error']}")

        success_count += batch_success
        fail_count += batch_fail

        batch_elapsed_ms = (time.perf_counter() - batch_start) * 1000
        avg_ms = sum(latencies) / len(latencies) if latencies else 0
        max_ms = max(latencies) if latencies else 0
        print(f"  Done: {batch_success} created, {batch_fail} failed | "
              f"batch: {batch_elapsed_ms:.0f}ms | "
              f"avg: {avg_ms:.0f}ms, max: {max_ms:.0f}ms")

        # Sleep between batches (skip after last batch)
        if batch_idx < total_batches - 1:
            print(f"  Sleeping {sleep_interval}s...")
            await asyncio.sleep(sleep_interval)

    overall_ms = (time.perf_counter() - overall_start) * 1000

    # Summary
    all_latencies = [r['elapsed_ms'] for r in results if r['success']]
    print()
    print(f"{'=' * 70}")
    print(f"Summary")
    print(f"{'=' * 70}")
    print(f"  Total:     {total}")
    print(f"  Success:   {success_count}")
    print(f"  Failed:    {fail_count}")
    print(f"  Duration:  {overall_ms:.0f}ms ({overall_ms / 1000:.1f}s)")
    if all_latencies:
        all_latencies.sort()
        p95_idx = min(int(len(all_latencies) * 0.95), len(all_latencies) - 1)
        print(f"  Avg:       {sum(all_latencies) / len(all_latencies):.0f}ms")
        print(f"  P95:       {all_latencies[p95_idx]:.0f}ms")
        print(f"  Max:       {max(all_latencies):.0f}ms")
        print(f"  Min:       {min(all_latencies):.0f}ms")
    print(f"{'=' * 70}")

    return created_ids, results


def main() -> None:
    _load_env_file()

    domain = os.getenv("E2B_DOMAIN", "")
    api_key = os.getenv("E2B_API_KEY", "")
    template = os.getenv("SANDBOX_TEMPLATE", "")
    timeout = int(os.getenv("SANDBOX_TIMEOUT", "300"))

    if not domain:
        print("Error: E2B_DOMAIN not set", file=sys.stderr)
        sys.exit(1)
    if not api_key:
        print("Error: E2B_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    if not template:
        print("Error: SANDBOX_TEMPLATE not set in .env", file=sys.stderr)
        sys.exit(1)

    os.environ["E2B_DOMAIN"] = domain
    os.environ["E2B_API_KEY"] = api_key

    print(f"E2B_DOMAIN: {domain}")
    print()

    created_ids, results = asyncio.run(batch_create(
        total=TOTAL,
        concurrency=CONCURRENCY,
        sleep_interval=SLEEP_INTERVAL,
        template=template,
        timeout=timeout,
    ))

    # Save results
    output_dir = Path(__file__).parent / "output" / "batch_create_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    ids_file = output_dir / f"sandbox_ids_{timestamp}.txt"
    ids_file.write_text("\n".join(created_ids) + "\n", encoding='utf-8')

    details_file = output_dir / f"details_{timestamp}.json"
    details_file.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    print(f"\nSandbox IDs saved to: {ids_file}")
    print(f"Details saved to: {details_file}")
    print(f"Created {len(created_ids)} sandboxes.")


if __name__ == "__main__":
    main()
