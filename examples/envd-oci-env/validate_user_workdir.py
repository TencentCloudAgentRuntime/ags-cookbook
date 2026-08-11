#!/usr/bin/env python3
"""Verify the OCI User / Workdir defaults on AGS through the E2B Python SDK.

This is the customer's actual path: the E2B SDK talks to the AGS E2B-compatible
data plane, which talks to envd, which starts the Linux child process. `agr` is
used only to prepare and clean up the Tool and Instance; every behavioral
assertion below goes through the SDK.

The contract under test (frozen product semantics):

    user=None,    cwd=None    -> the business image's OCI User,  its OCI Workdir
    user=<name>,  cwd=None    -> that user,                      its OCI Workdir
    user=None,    cwd=<path>  -> the OCI User,                   that path
    user=<name>,  cwd=<path>  -> that user,                      that path

Required environment:

    E2B_API_KEY     AGS key with its ark_ prefix replaced by e2b_
    E2B_DOMAIN      AGS data-plane domain, e.g. ap-hongkong.tencentags.com
    AGS_SANDBOX_ID  the instance id to connect to

Credentials are read from the environment only; nothing is printed.

Two AGS integration rules apply:

  * AGS issues API keys with an `ark_` prefix. Replace only that prefix with
    `e2b_`; the AGS data plane accepts the normalized form. SDK 2.35 still
    requires `E2B_VALIDATE_API_KEY=false` for AGS's non-hex key suffix.

  * Create the sandbox with Metadata Name `x-envd-version`, Value `0.4.0`.
    Without it, a deployment that misses every backend whitelist rule may report
    0.2.10 and make the SDK inject its historical default username `user`.

Usage:
    python validate_user_workdir.py <fixture>     # fixture is "a" or "b"
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

# What the envd artifact reports. The SDK compares this against its own
# ENVD_DEFAULT_USER gate (0.4.0) to decide whether to inject a legacy default
# username; 0.5.14 is above the gate, so it sends none.
ENVD_VERSION_STRING = "0.5.14"

# One shell probe reused by every case, so every assertion reads the same fields.
PROBE = (
    'printf "uid=%s\\n" "$(id -u)"; '
    'printf "gid=%s\\n" "$(id -g)"; '
    'printf "groups=%s\\n" "$(id -G)"; '
    'printf "user=%s\\n" "${USER-}"; '
    'printf "home=%s\\n" "${HOME-}"; '
    'printf "pwd=%s\\n" "$(pwd)"; '
    # The command's OWN capabilities. ACCEPTANCE 4.1 requires CapEff=0 for a
    # default command: a dropped process must not retain envd's capabilities.
    'printf "capeff=%s\\n" "$(awk \'/^CapEff:/{print $2}\' /proc/self/status)"; '
    'printf "PWD=%s\\n" "${PWD-}"; '
    'printf "fixture=%s\\n" "${FIXTURE_NAME-}"; '
    'printf "image_env=%s\\n" "${FIXTURE_IMAGE_ONLY-}"'
)

# Collected once per run: envd's own identity, the mounted file's metadata, and
# the mount flags. These are what make the setuid mechanism auditable.
ENVD_PROBE = (
    'printf "envd_uid=%s\\n" "$(awk \'/^Uid:/{print $2, $3, $4, $5}\' /proc/1/status)"; '
    'printf "envd_gid=%s\\n" "$(awk \'/^Gid:/{print $2, $3, $4, $5}\' /proc/1/status)"; '
    'printf "envd_groups=%s\\n" "$(awk \'/^Groups:/{for(i=2;i<=NF;i++) printf "%s%s", $i, (i<NF?" ":"")}\' /proc/1/status)"; '
    'printf "envd_capeff=%s\\n" "$(awk \'/^CapEff:/{print $2}\' /proc/1/status)"; '
    'printf "envd_no_new_privs=%s\\n" "$(awk \'/^NoNewPrivs:/{print $2}\' /proc/1/status)"; '
    'printf "envd_file=%s\\n" "$(stat -c \'%u:%g %04a\' "$ENVD_PATH" 2>/dev/null || echo unavailable)"; '
    'printf "envd_version=%s\\n" "$("$ENVD_PATH" -version 2>/dev/null || echo unavailable)"; '
    'printf "envd_commit=%s\\n" "$("$ENVD_PATH" -commit 2>/dev/null || echo unavailable)"; '
    'printf "mount_line=%s\\n" "$(grep -F "$ENVD_MOUNT" /proc/self/mountinfo | head -1 || echo none)"; '
    'printf "nosuid=%s\\n" "$(grep -F "$ENVD_MOUNT" /proc/self/mountinfo | head -1 | grep -c nosuid || true)"; '
    'printf "mount_ro=%s\\n" "$(grep -F "$ENVD_MOUNT" /proc/self/mountinfo | head -1 | awk \'$6 ~ /(^|,)ro(,|$)/ {print 1; found=1} END {if (!found) print 0}\')"'
)


@dataclass
class Fixture:
    key: str
    name: str
    uid: str
    gid: str
    groups: set
    workdir: str
    private_dir: Optional[str] = None
    other_user: Optional[str] = None
    other_uid: Optional[str] = None
    other_gid: Optional[str] = None
    other_groups: set = field(default_factory=set)


FIXTURES = {
    "a": Fixture(
        key="a",
        name="fixture-a",
        uid="10001",
        gid="10001",
        groups={"10001", "20001"},
        workdir="/opt/app/work",
        private_dir="/opt/app/private",
        other_user="otheruser",
        other_uid="10002",
        other_gid="10002",
        other_groups={"10002"},
    ),
    "b": Fixture(
        key="b",
        name="fixture-b",
        uid="61234",
        gid="61235",
        groups={"61235"},
        workdir="/srv/numeric/work",
    ),
}


class Report:
    """Records each assertion so the run ends with a matrix rather than a stack
    trace, and so an unexecuted case is reported as such instead of assumed."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def ok(self, case: str, what: str, value) -> None:
        self.rows.append((case, "PASS", f"{what} = {value!r}"))
        print(f"    PASS {what} = {value!r}")

    def fail(self, case: str, what: str, actual, expected) -> None:
        self.rows.append((case, "FAIL", f"{what}: got {actual!r}, expected {expected!r}"))
        print(f"    FAIL {what}: got {actual!r}, expected {expected!r}")

    def unverified(self, case: str, why: str) -> None:
        self.rows.append((case, "UNVERIFIED", why))
        print(f"    UNVERIFIED {case}: {why}")

    def check(self, case: str, what: str, actual, expected) -> None:
        if actual == expected:
            self.ok(case, what, actual)
        else:
            self.fail(case, what, actual, expected)

    @property
    def failed(self) -> int:
        return sum(1 for _, status, _ in self.rows if status == "FAIL")

    @property
    def passed(self) -> int:
        return sum(1 for _, status, _ in self.rows if status == "PASS")

    @property
    def unverified_count(self) -> int:
        return sum(1 for _, status, _ in self.rows if status == "UNVERIFIED")

    def summary(self) -> None:
        print()
        print("== matrix")
        for case, status, detail in self.rows:
            print(f"   {status:<10} {case:<28} {detail}")
        print()
        print(f"== {self.passed} passed, {self.failed} failed, "
              f"{self.unverified_count} unverified")


def parse(stdout: str) -> dict:
    values: dict[str, str] = {}
    for line in stdout.strip().splitlines():
        key, _, value = line.strip().partition("=")
        if key:
            values[key] = value
    return values


def connect_sandbox(sandbox_id: str):
    """Connect to an existing AGS instance with the E2B SDK."""
    from e2b import Sandbox

    return Sandbox.connect(sandbox_id)


async def validate_async_default(sandbox_id: str, fixture: Fixture, report: Report) -> None:
    """Exercise the required async no-user/no-cwd path without SDK patching."""
    from e2b import AsyncSandbox

    sandbox = await AsyncSandbox.connect(sandbox_id)
    got = parse((await sandbox.commands.run(PROBE)).stdout)
    case = f"{fixture.key}8/async-default"

    report.check(case, "uid", got.get("uid"), fixture.uid)
    report.check(case, "gid", got.get("gid"), fixture.gid)
    report.check(case, "groups", set((got.get("groups") or "").split()), fixture.groups)
    report.check(case, "pwd", got.get("pwd"), fixture.workdir)
    report.check(case, "PWD", got.get("PWD"), fixture.workdir)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in FIXTURES:
        print(__doc__)
        return 2

    fixture = FIXTURES[sys.argv[1]]

    for required in (
        "E2B_API_KEY",
        "E2B_DOMAIN",
        "AGS_SANDBOX_ID",
        "ENVD_EXPECTED_COMMIT",
    ):
        if not os.environ.get(required):
            print(f"{required} is required", file=sys.stderr)
            return 2

    envd_path = os.environ.get("ENVD_PATH", "/opt/envd/usr/bin/envd")
    envd_mount = os.environ.get("ENVD_MOUNT", "/opt/envd")

    sandbox = connect_sandbox(os.environ["AGS_SANDBOX_ID"])
    report = Report()

    print(f"== {fixture.name} on AGS via the E2B Python SDK")

    advertised_version = str(sandbox._envd_version)
    expected_advertised_version = os.environ.get("AGS_ENVD_VERSION_METADATA", "0.4.0")
    print(f"   control-plane envd version: {advertised_version}")
    report.check(
        "sdk/version-gate",
        "control-plane envd version",
        advertised_version,
        expected_advertised_version,
    )

    # ---- envd's own state, for the setuid audit trail -------------------------
    print("\n  [env] envd process, file metadata, and mount flags")
    envd_info = parse(
        sandbox.commands.run(
            ENVD_PROBE,
            envs={"ENVD_PATH": envd_path, "ENVD_MOUNT": envd_mount},
        ).stdout
    )
    for key in (
        "envd_uid",
        "envd_gid",
        "envd_groups",
        "envd_capeff",
        "envd_no_new_privs",
        "envd_file",
        "envd_version",
        "envd_commit",
        "mount_line",
        "mount_ro",
    ):
        if key in envd_info:
            print(f"    {key}: {envd_info[key]}")

    report.check("env/envd-version", "envd -version",
                 envd_info.get("envd_version"), ENVD_VERSION_STRING)
    report.check("env/envd-commit", "envd -commit",
                 envd_info.get("envd_commit"), os.environ["ENVD_EXPECTED_COMMIT"])
    report.check("env/envd-file", "envd owner/mode",
                 envd_info.get("envd_file"), "0:0 4755")
    report.check("env/envd-uid", "envd real/effective/saved/fs UID",
                 (envd_info.get("envd_uid") or "").split(),
                 [fixture.uid, "0", "0", "0"])
    report.check("env/envd-gid", "envd real/effective/saved/fs GID",
                 (envd_info.get("envd_gid") or "").split(), [fixture.gid] * 4)
    report.check("env/envd-groups", "envd supplementary groups",
                 set((envd_info.get("envd_groups") or "").split()), fixture.groups)
    report.check("env/no-new-privs", "NoNewPrivs",
                 envd_info.get("envd_no_new_privs"), "0")
    report.check("env/nosuid", "mount has nosuid", envd_info.get("nosuid"), "0")
    report.check("env/read-only", "Image Volume mount is read-only",
                 envd_info.get("mount_ro"), "1")

    cap_eff_text = envd_info.get("envd_capeff", "")
    try:
        cap_eff = int(cap_eff_text, 16)
    except ValueError:
        report.fail("env/capabilities", "CapEff hex value", cap_eff_text, "hexadecimal")
        cap_eff = 0
    else:
        report.ok("env/capabilities", "CapEff hex value", cap_eff_text)
    required_caps = (1 << 6) | (1 << 7)  # CAP_SETGID | CAP_SETUID
    report.check("env/capabilities", "CAP_SETGID and CAP_SETUID are effective",
                 cap_eff & required_caps, required_caps)

    # ---- A1 / B1: no user, no cwd -------------------------------------------
    print(f"\n  [{fixture.key}1] user=None, cwd=None -> OCI User + OCI Workdir")
    got = parse(sandbox.commands.run(PROBE).stdout)
    case = f"{fixture.key}1/default"
    report.check(case, "uid", got.get("uid"), fixture.uid)
    report.check(case, "gid", got.get("gid"), fixture.gid)
    report.check(case, "groups", set((got.get("groups") or "").split()), fixture.groups)
    report.check(case, "pwd", got.get("pwd"), fixture.workdir)
    report.check(case, "PWD", got.get("PWD"), fixture.workdir)
    report.check(case, "image env reached the command",
                 got.get("image_env"), "from-oci-image")
    report.check(case, "fixture marker", got.get("fixture"), fixture.name)
    # ACCEPTANCE 4.1: a default command must run with no capabilities. envd itself
    # legitimately holds capabilities under setuid; the command must not inherit them.
    report.check(case, "CapEff (command holds no capabilities)",
                 got.get("capeff"), "0000000000000000")

    # ---- A2 / B2: explicit root ---------------------------------------------
    print(f"\n  [{fixture.key}2] user='root', cwd=None -> root + OCI Workdir")
    got = parse(sandbox.commands.run(PROBE, user="root").stdout)
    case = f"{fixture.key}2/explicit-root"
    report.check(case, "uid", got.get("uid"), "0")
    report.check(case, "gid", got.get("gid"), "0")
    report.check(case, "groups", set((got.get("groups") or "").split()), {"0"})
    report.check(case, "pwd", got.get("pwd"), fixture.workdir)
    report.check(case, "PWD", got.get("PWD"), fixture.workdir)
    report.check(case, "USER", got.get("user"), "root")

    # ---- A4 / B4: explicit cwd ---------------------------------------------
    print(f"\n  [{fixture.key}4] user=None, cwd='/tmp' -> OCI User + /tmp")
    got = parse(sandbox.commands.run(PROBE, cwd="/tmp").stdout)
    case = f"{fixture.key}4/explicit-cwd"
    report.check(case, "uid", got.get("uid"), fixture.uid)
    report.check(case, "pwd", got.get("pwd"), "/tmp")
    report.check(case, "PWD", got.get("PWD"), "/tmp")

    # ---- A5 / B5: both explicit --------------------------------------------
    print(f"\n  [{fixture.key}5] user='root', cwd='/tmp' -> root + /tmp")
    got = parse(sandbox.commands.run(PROBE, user="root", cwd="/tmp").stdout)
    case = f"{fixture.key}5/explicit-both"
    report.check(case, "uid", got.get("uid"), "0")
    report.check(case, "pwd", got.get("pwd"), "/tmp")
    report.check(case, "PWD", got.get("PWD"), "/tmp")

    # ---- fixture A only: another user, unknown user, unreachable cwd --------
    if fixture.other_user:
        print(f"\n  [a3] user='{fixture.other_user}', cwd=None -> that user + OCI Workdir")
        got = parse(sandbox.commands.run(PROBE, user=fixture.other_user).stdout)
        report.check("a3/other-user", "uid", got.get("uid"), fixture.other_uid)
        report.check("a3/other-user", "gid", got.get("gid"), fixture.other_gid)
        report.check("a3/other-user", "groups",
                     set((got.get("groups") or "").split()), fixture.other_groups)
        report.check("a3/other-user", "pwd", got.get("pwd"), fixture.workdir)

        print("\n  [a6] unknown user -> must fail, never fall back to the default user")
        try:
            result = sandbox.commands.run(PROBE, user="ghost-user-7c1e")
            leaked = parse(result.stdout).get("uid")
            report.fail("a6/unknown-user", "request outcome",
                        f"succeeded as uid {leaked}", "an error")
        except Exception as exc:  # noqa: BLE001 - any refusal satisfies the contract
            message = str(exc)
            report.ok("a6/unknown-user", "rejected with", type(exc).__name__)
            report.check("a6/unknown-user", "error names the requested user",
                         "ghost-user-7c1e" in message, True)

        print("\n  [a7] otheruser + a directory it cannot enter -> error names user and cwd")
        try:
            result = sandbox.commands.run(
                PROBE, user=fixture.other_user, cwd=fixture.private_dir
            )
            report.fail("a7/unreachable-cwd", "request outcome",
                        f"succeeded in {parse(result.stdout).get('pwd')}", "an error")
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            report.ok("a7/unreachable-cwd", "rejected with", type(exc).__name__)
            report.check("a7/unreachable-cwd", "error names the user",
                         fixture.other_user in message, True)
            report.check("a7/unreachable-cwd", "error names the cwd",
                         fixture.private_dir in message, True)
    print(f"\n  [{fixture.key}8] async user=None, cwd=None -> OCI User + OCI Workdir")
    asyncio.run(validate_async_default(os.environ["AGS_SANDBOX_ID"], fixture, report))

    report.summary()

    return 1 if report.failed or report.unverified_count else 0


if __name__ == "__main__":
    sys.exit(main())
