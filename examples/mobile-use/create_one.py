#!/usr/bin/env python3
"""One-time script: create a single sandbox."""

from __future__ import annotations

import os
import sys
import time
import asyncio
from pathlib import Path


def _load_env_file() -> None:
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


async def create_one(template: str, timeout: int) -> None:
    from e2b import AsyncSandbox

    print(f"Creating sandbox (template={template}, timeout={timeout}s)...")
    start = time.perf_counter()
    sandbox = await AsyncSandbox.create(template=template, timeout=timeout)
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"Created: {sandbox.sandbox_id}  ({elapsed_ms:.0f}ms)")


def main() -> None:
    _load_env_file()

    domain = os.getenv("E2B_DOMAIN", "")
    api_key = os.getenv("E2B_API_KEY", "")
    template = os.getenv("SANDBOX_TEMPLATE", "")
    timeout = int(os.getenv("SANDBOX_TIMEOUT", "300"))

    if not domain or not api_key or not template:
        print("Error: E2B_DOMAIN, E2B_API_KEY, SANDBOX_TEMPLATE must be set in .env", file=sys.stderr)
        sys.exit(1)

    os.environ["E2B_DOMAIN"] = domain
    os.environ["E2B_API_KEY"] = api_key

    asyncio.run(create_one(template, timeout))


if __name__ == "__main__":
    main()
