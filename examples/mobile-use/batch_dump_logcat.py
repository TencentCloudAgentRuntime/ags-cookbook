#!/usr/bin/env python3
"""
Batch dump logcat logs from existing sandboxes.

Connects to each sandbox, retrieves full logcat logs via Appium,
saves them to output directory organized by sandbox ID, then disconnects
(without killing/deleting the sandbox).

Usage:
    # Dump logcat using a YAML config file
    python batch_dump_logcat.py --config sandboxes.yaml

    # Customize concurrency (default 5)
    python batch_dump_logcat.py --config sandboxes.yaml --concurrency 10

    # Customize output directory (default: output/dump_logcat_output)
    python batch_dump_logcat.py --config sandboxes.yaml --output-dir /tmp/logcat

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
from datetime import datetime
from typing import List, Dict, Any

# Script directory
SCRIPT_DIR = Path(__file__).parent
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output" / "batch_dump_logcat_output"


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


def format_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def dump_logcat_for_sandbox(
    sandbox_id: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """
    Connect to a single sandbox, dump logcat, and disconnect.

    Steps:
      1. Connect to existing sandbox via Sandbox.connect()
      2. Create Appium driver
      3. Execute 'logcat -d' to get all buffered logs
      4. Save logs to output_dir/<sandbox_id>/logcat_<timestamp>.txt
      5. Quit Appium driver (does NOT kill the sandbox)

    Args:
        sandbox_id: The sandbox ID to connect to.
        output_dir: Base output directory.

    Returns:
        Dict with result details (sandbox_id, success, file_path, error, etc.)
    """
    from e2b import Sandbox
    from appium import webdriver
    from appium.options.android import UiAutomator2Options
    from appium.webdriver.appium_connection import AppiumConnection
    from appium.webdriver.client_config import AppiumClientConfig

    result = {
        'sandbox_id': sandbox_id,
        'success': False,
        'file_path': '',
        'log_size_kb': 0,
        'line_count': 0,
        'error': '',
        'elapsed_ms': 0,
    }

    start = time.perf_counter()
    sandbox = None
    driver = None

    try:
        # Step 1: Connect to existing sandbox
        print(f"  [{format_timestamp()}] [{sandbox_id}] Connecting to sandbox...")
        sandbox = Sandbox.connect(sandbox_id)
        print(f"  [{format_timestamp()}] [{sandbox_id}] Sandbox connected")

        # Step 2: Create Appium driver with isolated connection class
        # NOTE: AppiumConnection.extra_headers is a shared class variable.
        # When running concurrently, multiple threads would overwrite each
        # other's token, causing "Authorization Required" errors.
        # Instead, create an isolated subclass per sandbox so each one
        # carries its own token.
        print(f"  [{format_timestamp()}] [{sandbox_id}] Connecting to Appium...")
        access_token = sandbox._envd_access_token

        class IsolatedConnection(AppiumConnection):
            extra_headers = {'X-Access-Token': access_token}

        options = UiAutomator2Options()
        options.platform_name = 'Android'
        options.automation_name = 'UiAutomator2'
        options.new_command_timeout = 600
        options.set_capability('adbExecTimeout', 300000)

        appium_url = f"https://{sandbox.get_host(4723)}"
        client_config = AppiumClientConfig(
            remote_server_addr=appium_url,
            timeout=300,
        )
        executor = IsolatedConnection(client_config=client_config)
        driver = webdriver.Remote(command_executor=executor, options=options)
        print(f"  [{format_timestamp()}] [{sandbox_id}] Appium connected (session: {driver.session_id})")

        # Step 3: Dump logcat
        print(f"  [{format_timestamp()}] [{sandbox_id}] Dumping logcat...")
        logcat_result = driver.execute_script('mobile: shell', {
            'command': 'logcat',
            'args': ['-d'],
        })

        if logcat_result:
            # Step 4: Save to file
            sandbox_output_dir = output_dir / sandbox_id
            sandbox_output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            logcat_filename = f"logcat_{timestamp}.txt"
            logcat_path = sandbox_output_dir / logcat_filename

            with open(logcat_path, 'w', encoding='utf-8') as f:
                f.write(logcat_result)

            file_size_kb = logcat_path.stat().st_size / 1024
            line_count = logcat_result.count('\n')

            result['success'] = True
            result['file_path'] = str(logcat_path)
            result['log_size_kb'] = round(file_size_kb, 2)
            result['line_count'] = line_count
            print(f"  [{format_timestamp()}] [{sandbox_id}] Logcat saved: {logcat_path} "
                  f"({file_size_kb:.1f} KB, {line_count} lines)")
        else:
            result['error'] = 'logcat returned empty result'
            print(f"  [{format_timestamp()}] [{sandbox_id}] Logcat returned empty result")

    except Exception as e:
        result['error'] = str(e)[:300]
        print(f"  [{format_timestamp()}] [{sandbox_id}] ERROR: {str(e)[:200]}")
    finally:
        # Step 5: Disconnect Appium (do NOT kill the sandbox)
        if driver is not None:
            try:
                driver.quit()
                print(f"  [{format_timestamp()}] [{sandbox_id}] Appium session closed")
            except Exception as e:
                print(f"  [{format_timestamp()}] [{sandbox_id}] Warning: error closing Appium (can be ignored): {e}")

        result['elapsed_ms'] = round((time.perf_counter() - start) * 1000, 1)

    return result


async def batch_dump_logcat(
    sandbox_ids: List[str],
    output_dir: Path,
    concurrency: int = 5,
) -> List[Dict[str, Any]]:
    """
    Dump logcat from multiple sandboxes with concurrency control.

    Args:
        sandbox_ids: List of sandbox IDs.
        output_dir: Output directory for logcat files.
        concurrency: Max concurrent operations.

    Returns:
        List of result dicts.
    """
    total = len(sandbox_ids)
    results: List[Dict[str, Any]] = []
    semaphore = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    print(f"Total sandboxes: {total}")
    print(f"Concurrency: {concurrency}")
    print(f"Output directory: {output_dir}")
    print()

    overall_start = time.perf_counter()

    async def _process_one(sid: str) -> Dict[str, Any]:
        async with semaphore:
            print(f"[{format_timestamp()}] [{sid}] Starting...")
            # Run the sync function in a thread to avoid blocking the event loop
            r = await loop.run_in_executor(
                None, dump_logcat_for_sandbox, sid, output_dir,
            )
            status = "OK" if r['success'] else f"FAILED: {r['error'][:80]}"
            print(f"[{format_timestamp()}] [{sid}] Done ({r['elapsed_ms']:.0f}ms) - {status}")
            return r

    tasks = [_process_one(sid) for sid in sandbox_ids]
    results = await asyncio.gather(*tasks)

    overall_ms = (time.perf_counter() - overall_start) * 1000

    # Summary
    success_count = sum(1 for r in results if r['success'])
    fail_count = total - success_count
    total_kb = sum(r['log_size_kb'] for r in results if r['success'])
    total_lines = sum(r['line_count'] for r in results if r['success'])

    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Total:       {total}")
    print(f"  Success:     {success_count}")
    print(f"  Failed:      {fail_count}")
    print(f"  Duration:    {overall_ms:.0f}ms ({overall_ms / 1000:.1f}s)")
    print(f"  Total logs:  {total_kb:.1f} KB, {total_lines} lines")
    print(f"  Output dir:  {output_dir}")

    if fail_count > 0:
        print()
        print("Failed sandboxes:")
        for r in results:
            if not r['success']:
                print(f"  - {r['sandbox_id']}: {r['error'][:120]}")

    print("=" * 70)

    return list(results)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch dump logcat logs from existing sandboxes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This tool connects to existing sandboxes, dumps full logcat logs,
and saves them organized by sandbox ID. It does NOT kill or delete
the sandboxes after dumping.

YAML config format:
    sandbox_ids:
      - sandbox_id_1
      - sandbox_id_2

Output structure:
    <output-dir>/
        <sandbox_id_1>/
            logcat_YYYYMMDD_HHMMSS.txt
        <sandbox_id_2>/
            logcat_YYYYMMDD_HHMMSS.txt
        ...
        summary_YYYYMMDD_HHMMSS.json

Usage examples:
    %(prog)s --config sandboxes.yaml
    %(prog)s --config sandboxes.yaml --concurrency 10
    %(prog)s --config sandboxes.yaml --output-dir /tmp/logcat
        """,
    )

    parser.add_argument("--config", type=str, default=str(SCRIPT_DIR / "sandboxes.yaml"),
                        help="YAML config file containing sandbox_ids list (default: sandboxes.yaml)")
    parser.add_argument("--concurrency", "-c", type=int, default=5, help="Max concurrent operations (default: 5)")
    parser.add_argument("--output-dir", "-o", type=str, default=None, help="Output directory (default: output/dump_logcat_output)")

    return parser.parse_args()


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


def main() -> None:
    args = parse_arguments()
    sandbox_ids = load_sandbox_ids_from_yaml(args.config)

    if not sandbox_ids:
        print("Error: no sandbox IDs found in YAML config file.", file=sys.stderr)
        sys.exit(1)

    # Load environment
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

    # Determine output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Batch Logcat Dump Tool")
    print("=" * 70)
    print(f"E2B_DOMAIN:  {domain}")
    print(f"Sandboxes:   {len(sandbox_ids)}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Output dir:  {output_dir}")
    print("=" * 70)
    print()

    # Run batch dump
    results = asyncio.run(batch_dump_logcat(
        sandbox_ids=sandbox_ids,
        output_dir=output_dir,
        concurrency=args.concurrency,
    ))

    # Save summary JSON
    import json
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_file = output_dir / f"summary_{timestamp}.json"
    summary_file.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )
    print(f"\nSummary saved to: {summary_file}")

    # Exit code: 1 if any failures
    fail_count = sum(1 for r in results if not r['success'])
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
