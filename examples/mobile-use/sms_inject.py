#!/usr/bin/env python3
"""
Simulate an incoming SMS on an AGS mobile sandbox.

The mobile sandbox runs containerized Android (redroid), which has no emulator
console, so `adb emu sms send` is not available. The sandbox image ships an
equivalent device-side tool, `/system/bin/smartrun-sms-inject`, that writes a
received SMS (and its conversation thread) into the system SMS database. The
message then shows up in `content://sms/inbox` and in SMS apps.

Three ways to call it, pick the one that matches how you reach the sandbox:

1. adb + stdin   (`--from-stdin`): line 1 is the sender number, the rest is
   the message body.
2. adb + base64  (`--b64`): sender and body are each base64-encoded and passed
   as arguments. Use this when your caller can only pass command-line
   arguments to adb (no stdin), e.g. behind a wrapper that forwards argv.
3. SDK / Appium  (`--b64`): `mobile: shell` has no stdin, so base64 again.

None of them is shell-parsed, so quotes, `$`, backticks, newlines, CJK and
emoji are stored byte-for-byte. Do NOT use the plain argument form
`smartrun-sms-inject '<number>' '<message>'`: the arguments are parsed by
both the local and the device shell, and a message with spaces or quotes is
truncated (e.g. "plain arg msg" is stored as "plain").

Known limitation: an SMS app that is already open does not refresh until it is
reopened (the write does not trigger a content observer notification).

Requires a sandbox image that ships smartrun-sms-inject (SmartRun redroid
android_world image v33.3 or later).

Usage:
    # adb + stdin (default). Get the adb address from
    # `agr instance mobile connect <sandbox_id>`.
    uv run sms_inject.py adb --serial 127.0.0.1:5555 +8613800000000 "Hello"

    # adb + base64
    uv run sms_inject.py adb --serial 127.0.0.1:5555 --method b64 +8613800000000 "Hello"

    # SDK / Appium (needs E2B_API_KEY and E2B_DOMAIN)
    uv run sms_inject.py sdk --sandbox-id <sandbox_id> +8613800000000 "Hello"

Equivalent shell one-liners (no Python):
    # adb + stdin
    printf '%s\\n%s' "$NUM" "$MSG" | adb -s "$SERIAL" shell smartrun-sms-inject --from-stdin
    # adb + base64. GNU base64 wraps at 76 columns: pass -w0 on Linux
    # (macOS does not wrap). A wrapped value makes the device shell run the
    # extra lines as commands and the message is silently truncated.
    adb -s "$SERIAL" shell smartrun-sms-inject --b64 \\
        "$(printf '%s' "$NUM" | base64 -w0)" "$(printf '%s' "$MSG" | base64 -w0)"
"""

import argparse
import base64
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

SCRIPT_DIR = Path(__file__).parent
SMS_INJECT_TOOL = "smartrun-sms-inject"
ADB_TIMEOUT_SECONDS = 30


def _load_env_file() -> None:
    """Load .env next to this script (environment variables take precedence)."""
    env_file = SCRIPT_DIR / ".env"
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file)
    except ImportError:
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def _b64(text: str) -> str:
    """Standard, unwrapped base64; only [A-Za-z0-9+/=], safe as a shell word."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _validate(number: str, message: str) -> None:
    if not number or "\n" in number or "\r" in number:
        raise ValueError("number must be a non-empty single line")
    if not message:
        raise ValueError("message must not be empty")


def _check_adb_result(result: subprocess.CompletedProcess) -> None:
    # adb shell forwards the device-side exit status; the tool writes the
    # reason to stderr on failure.
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", "replace").strip()
        raise RuntimeError(f"{SMS_INJECT_TOOL} failed (exit {result.returncode}): {detail}")


# ==================== adb, method 1: stdin ====================


def inject_sms_via_adb(serial: str, number: str, message: str, adb: str = "adb") -> None:
    """Inject a received SMS over adb, passing the content on stdin (--from-stdin).

    Args:
        serial: adb serial, e.g. "127.0.0.1:5555" (as listed by `adb devices`).
        number: Sender number.
        message: Message body; may contain newlines and any characters.
            Trailing newlines are dropped by the tool.
        adb: Path to the adb binary.

    Raises:
        ValueError: Invalid number or empty message.
        RuntimeError: The tool failed (e.g. the image does not ship it).
    """
    _validate(number, message)
    # argv list: no local shell. Content goes over stdin: no device-side parsing.
    result = subprocess.run(
        [adb, "-s", serial, "shell", SMS_INJECT_TOOL, "--from-stdin"],
        input=f"{number}\n{message}".encode(),
        capture_output=True,
        timeout=ADB_TIMEOUT_SECONDS,
        check=False,
    )
    _check_adb_result(result)


# ==================== adb, method 2: base64 arguments ====================


def inject_sms_via_adb_b64(serial: str, number: str, message: str, adb: str = "adb") -> None:
    """Inject a received SMS over adb, passing base64 arguments (--b64).

    Does not need stdin, so it works when the caller can only pass arguments.

    Args:
        serial: adb serial, e.g. "127.0.0.1:5555".
        number: Sender number.
        message: Message body; may contain newlines and any characters.
            Trailing newlines are dropped by the tool.
        adb: Path to the adb binary.

    Raises:
        ValueError: Invalid number or empty message.
        RuntimeError: The tool failed (e.g. the image does not ship it).
    """
    _validate(number, message)
    result = subprocess.run(
        [adb, "-s", serial, "shell", SMS_INJECT_TOOL, "--b64", _b64(number), _b64(message)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=ADB_TIMEOUT_SECONDS,
        check=False,
    )
    _check_adb_result(result)


# ==================== SDK (e2b + Appium) ====================


def inject_sms_via_appium(driver, number: str, message: str) -> None:
    """Inject a received SMS through Appium `mobile: shell` (--b64).

    Args:
        driver: Appium WebDriver connected to the sandbox (see connect_appium).
        number: Sender number.
        message: Message body; may contain newlines and any characters.
            Trailing newlines are dropped by the tool.

    Raises:
        ValueError: Invalid number or empty message.
        RuntimeError: The tool failed (e.g. the image does not ship it).
    """
    _validate(number, message)
    # Pass the whole command in `command` (no `args`): Appium joins them with
    # spaces for the device shell anyway. base64 values contain no shell
    # metacharacters. `echo rc=$?` keeps the command at exit 0 (mobile: shell
    # raises otherwise) and reports the tool's exit status on stdout.
    output = driver.execute_script(
        "mobile: shell",
        {
            "command": f"{SMS_INJECT_TOOL} --b64 {_b64(number)} {_b64(message)} 2>&1; echo rc=$?",
            "timeout": ADB_TIMEOUT_SECONDS * 1000,
        },
    )
    if isinstance(output, dict):
        output = output.get("stdout", "") or ""
    output = str(output)
    if not re.search(r"^rc=0\r?$", output, re.MULTILINE):
        raise RuntimeError(f"{SMS_INJECT_TOOL} failed: {output.strip()}")


def connect_appium(sandbox):
    """Create an Appium WebDriver for an e2b Sandbox (same as sandbox_connect.py)."""
    from appium import webdriver
    from appium.options.android import UiAutomator2Options
    from appium.webdriver.appium_connection import AppiumConnection
    from appium.webdriver.client_config import AppiumClientConfig

    access_token = sandbox._envd_access_token

    class _Connection(AppiumConnection):
        extra_headers: ClassVar[dict[str, str]] = {"X-Access-Token": access_token}

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.new_command_timeout = 600

    executor = _Connection(
        client_config=AppiumClientConfig(
            remote_server_addr=f"https://{sandbox.get_host(4723)}", timeout=300
        )
    )
    return webdriver.Remote(command_executor=executor, options=options)


# ==================== CLI ====================


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject a received SMS into an AGS mobile sandbox")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_adb = sub.add_parser("adb", help="inject over adb")
    p_adb.add_argument("--serial", required=True, help="adb serial, e.g. 127.0.0.1:5555")
    p_adb.add_argument("--adb", default="adb", help="path to the adb binary")
    p_adb.add_argument(
        "--method",
        choices=("stdin", "b64"),
        default="stdin",
        help="stdin: content on stdin (default); b64: base64 arguments",
    )

    p_sdk = sub.add_parser("sdk", help="inject through the e2b SDK + Appium")
    p_sdk.add_argument("--sandbox-id", required=True, help="sandbox ID (needs E2B_API_KEY, E2B_DOMAIN)")

    for p in (p_adb, p_sdk):
        p.add_argument("number", help="sender number")
        p.add_argument("message", help="message body")

    args = parser.parse_args()

    try:
        if args.mode == "adb":
            inject = inject_sms_via_adb_b64 if args.method == "b64" else inject_sms_via_adb
            inject(args.serial, args.number, args.message, adb=args.adb)
        else:
            _load_env_file()
            for name in ("E2B_API_KEY", "E2B_DOMAIN"):
                if not os.getenv(name):
                    raise RuntimeError(f"{name} is required for sdk mode")
            from e2b import Sandbox

            driver = connect_appium(Sandbox.connect(args.sandbox_id))
            try:
                inject_sms_via_appium(driver, args.number, args.message)
            finally:
                driver.quit()
    except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"SMS injected: from={args.number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
